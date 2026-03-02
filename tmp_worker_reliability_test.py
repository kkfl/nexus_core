"""Worker Reliability Test Orchestrator v2.

Uses docker compose environment override files for test flags.
Runs against a live Docker stack from the host.
"""
import json
import os
import subprocess
import sys
import time

import httpx

API = "http://localhost:8000"
COMPOSE_DIR = os.path.dirname(os.path.abspath(__file__))


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def docker(*args):
    cmd = ["docker", "compose"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=COMPOSE_DIR)
    out = result.stdout.strip()
    if out:
        lines = [l for l in out.split('\n') if 'obsolete' not in l]
        if lines:
            print(f"  [docker] {lines[0][:200]}")
    return result


def get_token(client):
    r = client.post(f"{API}/auth/login", data={
        "username": "admin@nexus.local", "password": "admin_password"
    })
    r.raise_for_status()
    return r.json()["access_token"]


def query_doc(client, headers, doc_id):
    r = client.get(f"{API}/kb/documents/{doc_id}", headers=headers)
    return r.json() if r.status_code == 200 else None


def query_chunks(client, headers, doc_id):
    r = client.get(f"{API}/kb/documents/{doc_id}/chunks", headers=headers)
    return r.json() if r.status_code == 200 else []


def query_events(client, headers, event_type=None, limit=20):
    params = {"limit": limit}
    if event_type:
        params["event_type"] = event_type
    r = client.get(f"{API}/events", headers=headers, params=params)
    return r.json().get("events", []) if r.status_code == 200 else []


def worker_logs(lines=50):
    result = subprocess.run(
        ["docker", "compose", "logs", "--tail", str(lines), "nexus-worker"],
        capture_output=True, text=True, cwd=COMPOSE_DIR
    )
    return result.stdout


def write_env_override(env_vars: dict):
    """Write a temporary .env.worker file with extra env vars for the worker."""
    # Read existing .env
    env_path = os.path.join(COMPOSE_DIR, ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()

    # Remove old test flags
    lines = [l for l in lines if not l.strip().startswith("RAG_TEST_")]

    # Append new flags
    for k, v in env_vars.items():
        lines.append(f"{k}={v}\n")

    with open(env_path, "w") as f:
        f.writelines(lines)


def clear_test_flags():
    """Remove test flags from .env."""
    env_path = os.path.join(COMPOSE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
        lines = [l for l in lines if not l.strip().startswith("RAG_TEST_")]
        with open(env_path, "w") as f:
            f.writelines(lines)


def restart_worker_with_flags(flags: dict):
    """Stop worker, set env flags, rebuild and restart."""
    docker("stop", "nexus-worker")
    time.sleep(2)
    write_env_override(flags)
    docker("up", "-d", "--no-deps", "--force-recreate", "nexus-worker")
    time.sleep(8)


def restart_worker_clean():
    """Stop worker, clear test flags, restart."""
    docker("stop", "nexus-worker")
    time.sleep(2)
    clear_test_flags()
    docker("up", "-d", "--no-deps", "--force-recreate", "nexus-worker")
    time.sleep(8)


# =====================================================================
#  TEST 1: URL Ingest Interrupt
# =====================================================================
def test_url_interrupt(client, headers, source_id):
    section("TEST 1: URL Ingest - Mid-Ingest Interrupt")

    # Step 1: Restart worker with slow flag
    print("  [1] Restarting worker with RAG_TEST_SLOW_STAGE=1...")
    restart_worker_with_flags({"RAG_TEST_SLOW_STAGE": "1"})

    # Step 2: Trigger URL ingest (with retry in case API is recovering)
    print("  [2] Triggering URL ingest...")
    for attempt in range(3):
        try:
            r = client.post(f"{API}/kb/documents/url", json={
                "url": "https://example.com",
                "source_id": source_id,
                "namespace": "global",
                "title": "Worker Interrupt Test URL"
            }, headers=headers)
            print(f"      POST -> {r.status_code}: {r.text[:150]}")
            break
        except Exception as e:
            print(f"      Attempt {attempt+1} failed: {e}")
            time.sleep(3)
    else:
        return {"test": "URL Interrupt", "result": "FAIL", "reason": "API unreachable"}

    # Step 3: Wait for processing to start
    print("  [3] Waiting 8s for job to start processing...")
    time.sleep(8)

    # Find the doc (it's created by _ingest_url before embed)
    r2 = client.get(f"{API}/kb/documents?namespace=global", headers=headers)
    docs = r2.json()
    test_doc = None
    for d in reversed(docs):
        if d.get("title") == "Worker Interrupt Test URL":
            test_doc = d
            break

    if not test_doc:
        print("  WARN: Doc not found by title, using most recent")
        test_doc = docs[-1] if docs else None

    if not test_doc:
        return {"test": "URL Interrupt", "result": "FAIL", "reason": "No doc created"}

    doc_id = test_doc["id"]
    print(f"      Doc id={doc_id} status={test_doc['ingest_status']}")

    # Step 4: Kill the worker mid-ingest
    print("  [4] Stopping worker mid-ingest (docker compose stop)...")
    docker("stop", "nexus-worker")
    time.sleep(3)

    doc = query_doc(client, headers, doc_id)
    status_after_kill = doc["ingest_status"] if doc else "unknown"
    print(f"      Status after kill: {status_after_kill}")

    # Step 5: Restart clean worker (startup recovery should fire)
    print("  [5] Restarting clean worker (startup recovery expected)...")
    restart_worker_clean()
    print("      Waiting 15s for startup recovery + re-ingest...")
    time.sleep(15)

    # Step 6: Verify
    doc = query_doc(client, headers, doc_id)
    final_status = doc["ingest_status"] if doc else "unknown"
    chunks = query_chunks(client, headers, doc_id)
    error_msg = doc.get("error_message") if doc else None

    logs = worker_logs(80)
    recovery_found = "startup" in logs.lower() and "recover" in logs.lower()

    print(f"      Final status: {final_status}")
    print(f"      Chunks: {len(chunks)}")
    print(f"      Error msg: {error_msg}")
    print(f"      Recovery in logs: {recovery_found}")

    result = "PASS" if final_status == "ready" and len(chunks) > 0 else "FAIL"
    print(f"\n  >>> RESULT: {result}")

    return {
        "test": "URL Interrupt",
        "result": result,
        "status_after_kill": status_after_kill,
        "final_status": final_status,
        "chunks": len(chunks),
        "recovery_in_logs": recovery_found,
    }


# =====================================================================
#  TEST 2: Email Ingest Interrupt
# =====================================================================
def test_email_interrupt(client, headers, source_id):
    section("TEST 2: Email Ingest - Mid-Ingest Interrupt")

    # Step 1: Restart worker with slow flag
    print("  [1] Restarting worker with RAG_TEST_SLOW_STAGE=1...")
    restart_worker_with_flags({"RAG_TEST_SLOW_STAGE": "1"})

    # Step 2: Trigger email ingest
    print("  [2] Triggering email ingest...")
    r = client.post(f"{API}/kb/documents/email-ingest", json={
        "source_id": source_id,
        "namespace": "global",
        "subject": "Worker Interrupt Test Email",
        "body_text": "This is a test email body for reliability testing. " * 15,
        "sender": "reliability@test.com",
        "message_id": f"reliability-email-{int(time.time())}"
    }, headers=headers)
    print(f"      Response: {r.status_code}: {r.text[:150]}")

    if r.status_code != 200:
        return {"test": "Email Interrupt", "result": "FAIL", "reason": f"API {r.status_code}"}

    doc_id = r.json().get("document_id")
    print(f"      Doc id={doc_id}")

    # Step 3: Wait then kill
    print("  [3] Waiting 8s then killing worker...")
    time.sleep(8)
    docker("stop", "nexus-worker")
    time.sleep(3)

    doc = query_doc(client, headers, doc_id)
    status_after_kill = doc["ingest_status"] if doc else "unknown"
    print(f"      Status after kill: {status_after_kill}")

    # Step 4: Restart clean worker
    print("  [4] Restarting clean worker...")
    restart_worker_clean()
    print("      Waiting 15s for recovery...")
    time.sleep(15)

    doc = query_doc(client, headers, doc_id)
    final_status = doc["ingest_status"] if doc else "unknown"
    chunks = query_chunks(client, headers, doc_id)

    print(f"      Final status: {final_status}")
    print(f"      Chunks: {len(chunks)}")

    result = "PASS" if final_status == "ready" and len(chunks) > 0 else "FAIL"
    print(f"\n  >>> RESULT: {result}")

    return {
        "test": "Email Interrupt",
        "result": result,
        "status_after_kill": status_after_kill,
        "final_status": final_status,
        "chunks": len(chunks),
    }


# =====================================================================
#  TEST 3: Forced Failure
# =====================================================================
def test_forced_failure(client, headers, source_id):
    section("TEST 3: Forced Failure (RAG_TEST_FAIL_STAGE=chunk)")

    # Step 1: Restart worker with fail flag
    print("  [1] Restarting worker with RAG_TEST_FAIL_STAGE=chunk...")
    restart_worker_with_flags({"RAG_TEST_FAIL_STAGE": "chunk"})

    # Step 2: Trigger text ingest
    print("  [2] Triggering text ingest...")
    r = client.post(f"{API}/kb/documents/text", json={
        "source_id": source_id,
        "namespace": "global",
        "title": "Forced Failure Test Doc",
        "text": "This document will fail during chunk stage due to the test flag."
    }, headers=headers)
    print(f"      Response: {r.status_code}: {r.text[:150]}")

    if r.status_code != 200:
        return {"test": "Forced Failure", "result": "FAIL", "reason": f"API {r.status_code}"}

    doc_id = r.json().get("document_id")
    print(f"      Doc id={doc_id}")

    # Step 3: Wait for failure
    print("  [3] Waiting 15s for failure to propagate...")
    time.sleep(15)

    doc = query_doc(client, headers, doc_id)
    status = doc["ingest_status"] if doc else "unknown"
    error_msg = doc.get("error_message", "") or "" if doc else ""

    chunks = query_chunks(client, headers, doc_id)

    # Check events
    failed_events = query_events(client, headers, "kb.document.ingest_failed")
    has_failed_event = any(
        str(doc_id) == str(e.get("correlation_id", ""))
        for e in failed_events
    )

    # Check DLQ
    r = client.get(f"{API}/events/dlq", headers=headers)
    dlq_count = r.json().get("count", 0) if r.status_code == 200 else -1

    print(f"      ingest_status: {status}")
    print(f"      error_message: {error_msg[:200]}")
    print(f"      chunks: {len(chunks)}")
    print(f"      ingest_failed event: {has_failed_event}")
    print(f"      DLQ count: {dlq_count}")

    # Check worker logs for the error
    logs = worker_logs(30)
    forced_error_logged = "forced chunk failure" in logs.lower()
    print(f"      Error in worker logs: {forced_error_logged}")

    # Step 4: Clean up — restart normal worker
    print("  [4] Restarting clean worker...")
    restart_worker_clean()
    time.sleep(3)

    result = "PASS" if status == "failed" and "forced chunk failure" in error_msg else "FAIL"
    print(f"\n  >>> RESULT: {result}")

    return {
        "test": "Forced Failure",
        "result": result,
        "final_status": status,
        "error_message": error_msg[:200],
        "chunks": len(chunks),
        "failed_event": has_failed_event,
        "dlq_count": dlq_count,
        "error_in_logs": forced_error_logged,
    }


# =====================================================================
#  MAIN
# =====================================================================
def main():
    print("Worker Reliability Test Suite v2")
    print("=" * 70)

    client = httpx.Client(timeout=30)
    token = get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    print("  Auth: OK")

    r = client.get(f"{API}/kb/sources", headers=headers)
    source_id = r.json()[0]["id"] if r.json() else 1
    print(f"  Source id: {source_id}")

    results = []
    results.append(test_url_interrupt(client, headers, source_id))
    results.append(test_email_interrupt(client, headers, source_id))
    results.append(test_forced_failure(client, headers, source_id))

    section("FINAL RESULTS")
    for r in results:
        print(f"  {r['test']}: {r['result']}")
        for k, v in r.items():
            if k not in ("test", "result"):
                print(f"    {k}: {v}")

    all_pass = all(r["result"] == "PASS" for r in results)
    print(f"\n  Overall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    print("\nDone.")


if __name__ == "__main__":
    main()
