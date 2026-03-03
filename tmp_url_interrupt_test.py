"""Isolated Text/URL Interrupt Test — uses text ingest so doc exists before worker."""

import json
import os
import subprocess
import sys
import time

import httpx

API = "http://localhost:8000"
COMPOSE_DIR = os.path.dirname(os.path.abspath(__file__))


def docker(*args):
    cmd = ["docker", "compose"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=COMPOSE_DIR)
    out = result.stdout.strip()
    if out:
        lines = [l for l in out.split("\n") if "obsolete" not in l]
        if lines:
            print(f"  [docker] {lines[0][:200]}")
    return result


def write_env_override(env_vars: dict):
    env_path = os.path.join(COMPOSE_DIR, ".env")
    with open(env_path, "r") as f:
        lines = f.readlines()
    lines = [l for l in lines if not l.strip().startswith("RAG_TEST_")]
    for k, v in env_vars.items():
        lines.append(f"{k}={v}\n")
    with open(env_path, "w") as f:
        f.writelines(lines)


def clear_test_flags():
    env_path = os.path.join(COMPOSE_DIR, ".env")
    with open(env_path, "r") as f:
        lines = f.readlines()
    lines = [l for l in lines if not l.strip().startswith("RAG_TEST_")]
    with open(env_path, "w") as f:
        f.writelines(lines)


def main():
    print("=" * 70)
    print("  TEXT INGEST INTERRUPT TEST")
    print("=" * 70)

    client = httpx.Client(timeout=30)
    r = client.post(
        f"{API}/auth/login", data={"username": "admin@nexus.local", "password": "admin_password"}
    )
    r.raise_for_status()
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("  Auth: OK")

    r = client.get(f"{API}/kb/sources", headers=headers)
    source_id = r.json()[0]["id"]

    # Step 1: Stop worker, set slow flag, restart
    print("\n  [1] Restarting worker with RAG_TEST_SLOW_STAGE=1...")
    docker("stop", "nexus-worker")
    time.sleep(2)
    write_env_override({"RAG_TEST_SLOW_STAGE": "1"})
    docker("up", "-d", "--no-deps", "--force-recreate", "nexus-worker")
    time.sleep(10)

    # Step 2: Ingest via text (doc created by API before worker touches it)
    unique_title = f"Interrupt Test {int(time.time())}"
    print(f"\n  [2] Creating text doc: '{unique_title}'...")
    r = client.post(
        f"{API}/kb/documents/text",
        json={
            "source_id": source_id,
            "namespace": "global",
            "title": unique_title,
            "text": "This is a test document for worker interrupt testing. " * 10,
        },
        headers=headers,
    )
    print(f"      POST -> {r.status_code}: {r.text[:200]}")
    doc_id = r.json()["document_id"]
    print(f"      Doc id={doc_id}")

    # Step 3: Wait for processing to start (slow stage will hold 30s)
    print("\n  [3] Waiting 10s for job to hit slow stage...")
    time.sleep(10)

    r = client.get(f"{API}/kb/documents/{doc_id}", headers=headers)
    doc = r.json()
    pre_kill_status = doc["ingest_status"]
    print(f"      Status before kill: {pre_kill_status}")

    # Step 4: Kill worker mid-ingest
    print("\n  [4] Stopping worker mid-ingest...")
    docker("stop", "nexus-worker")
    time.sleep(3)

    r = client.get(f"{API}/kb/documents/{doc_id}", headers=headers)
    doc = r.json()
    status_after_kill = doc["ingest_status"]
    print(f"      Status after kill: {status_after_kill}")

    # Step 5: Restart clean worker with startup recovery
    print("\n  [5] Restarting clean worker (recovery expected)...")
    clear_test_flags()
    docker("up", "-d", "--no-deps", "--force-recreate", "nexus-worker")
    print("      Waiting 20s for startup recovery + re-ingest...")
    time.sleep(20)

    # Step 6: Verify
    r = client.get(f"{API}/kb/documents/{doc_id}", headers=headers)
    doc = r.json()
    final_status = doc["ingest_status"]
    error_msg = doc.get("error_message")

    r = client.get(f"{API}/kb/documents/{doc_id}/chunks", headers=headers)
    chunks = r.json() if r.status_code == 200 else []

    # Worker logs
    result = subprocess.run(
        ["docker", "compose", "logs", "--tail", "100", "nexus-worker"],
        capture_output=True,
        text=True,
        cwd=COMPOSE_DIR,
    )
    logs = result.stdout

    print(f"\n  RESULTS:")
    print(f"      Pre-kill status:   {pre_kill_status}")
    print(f"      Status after kill: {status_after_kill}")
    print(f"      Final status:      {final_status}")
    print(f"      Chunks:            {len(chunks)}")
    print(f"      Error message:     {error_msg}")

    # Show recovery log lines
    print(f"\n  Recovery log lines:")
    for line in logs.split("\n"):
        if "[startup]" in line or "recover" in line.lower() or "[TEST]" in line:
            print(f"      {line.strip()[:150]}")

    if final_status == "ready" and len(chunks) > 0:
        print(f"\n  >>> RESULT: PASS")
    elif status_after_kill == "processing" and final_status == "ready":
        print(f"\n  >>> RESULT: PASS (with recovery)")
    else:
        print(f"\n  >>> RESULT: FAIL")

    print("\nDone.")


if __name__ == "__main__":
    main()
