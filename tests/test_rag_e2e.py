"""
RAG End-to-End Test — Python
============================
Tests the full RAG pipeline against the live Nexus API:
  1. Login
  2. Create KB source
  3. Ingest text document
  4. Wait for embedding completion
  5. Search KB with a semantically relevant query
  6. Verify results contain the ingested content

Usage:
    python tests/test_rag_e2e.py

Requires: httpx  (pip install httpx)
All Docker services must be running (docker compose up).
"""

import asyncio
import os
import sys
import time

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
# ---------- try to import httpx, give a helpful message if missing ----------
try:
    import httpx
except ImportError:
    print("ERROR: httpx is required.  Install it with:  pip install httpx")
    sys.exit(1)

# ---------- Configuration ----------------------------------------------------
API_URL = os.environ.get("NEXUS_API_URL", "http://localhost:8000")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@nexus.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin_password")
TIMEOUT = 90  # seconds to wait for embeddings (model download on cold start can be slow)


# ---------- Helpers -----------------------------------------------------------
def banner(label: str):
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")


def ok(msg: str):
    print(f"  ✅ {msg}")


def fail(msg: str):
    print(f"  ❌ {msg}")


# ---------- Main test ---------------------------------------------------------
async def run():
    results: dict[str, str] = {}
    async with httpx.AsyncClient(base_url=API_URL, timeout=15) as client:
        # ── Step 1: Login ─────────────────────────────────────────────
        banner("Step 1: Login")
        resp = await client.post(
            "/auth/login",
            data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if resp.status_code != 200:
            fail(f"Login failed ({resp.status_code}): {resp.text}")
            results["Login"] = "FAIL"
            print("\n⛔  Cannot proceed without authentication.")
            _print_summary(results)
            return
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        ok(f"Logged in as {ADMIN_EMAIL}")
        results["Login"] = "PASS"

        # ── Step 2: Create / reuse KB source ──────────────────────────
        banner("Step 2: Ensure KB Source")
        resp = await client.get("/kb/sources", headers=headers)
        sources = resp.json()
        if sources:
            source_id = sources[0]["id"]
            ok(f"Reusing existing source id={source_id}")
        else:
            resp = await client.post(
                "/kb/sources",
                json={"name": "E2E Test Source", "kind": "manual"},
                headers=headers,
            )
            if resp.status_code not in (200, 201):
                fail(f"Create source failed ({resp.status_code}): {resp.text}")
                results["Create Source"] = "FAIL"
                _print_summary(results)
                return
            source_id = resp.json()["id"]
            ok(f"Created source id={source_id}")
        results["Create Source"] = "PASS"

        # ── Step 3: Ingest text document ──────────────────────────────
        banner("Step 3: Ingest Text Document")
        unique_marker = f"nexus-rag-e2e-{int(time.time())}"
        doc_text = (
            f"The Nexus Core platform manages infrastructure agents. "
            f"The primary orchestration server IP is 10.42.0.1. "
            f"All DNS agents must register via the agent-registry service. "
            f"Marker: {unique_marker}"
        )
        resp = await client.post(
            "/kb/documents/text",
            json={
                "source_id": source_id,
                "namespace": "global",
                "title": f"E2E RAG Test Doc — {unique_marker}",
                "text": doc_text,
            },
            headers=headers,
        )
        if resp.status_code not in (200, 201):
            fail(f"Ingest failed ({resp.status_code}): {resp.text}")
            results["Ingest Document"] = "FAIL"
            _print_summary(results)
            return
        doc_id = resp.json()["document_id"]
        ok(f"Ingested document id={doc_id}")
        results["Ingest Document"] = "PASS"

        # ── Step 4: Wait for embedding ────────────────────────────────
        banner("Step 4: Wait for Embedding")
        deadline = time.monotonic() + TIMEOUT
        ready = False
        while time.monotonic() < deadline:
            resp = await client.get(f"/kb/documents/{doc_id}", headers=headers)
            status = resp.json().get("ingest_status", "unknown")
            print(f"    status = {status}")
            if status == "ready":
                ready = True
                break
            await asyncio.sleep(2)

        if not ready:
            fail(f"Document {doc_id} did not reach 'ready' within {TIMEOUT}s")
            results["Embedding"] = "FAIL"
            _print_summary(results)
            return
        ok(f"Document {doc_id} embedded and ready")
        results["Embedding"] = "PASS"

        # ── Step 5: RAG Search ────────────────────────────────────────
        banner("Step 5: RAG Search")
        resp = await client.post(
            "/kb/search",
            json={
                "query": "What is the primary orchestration server IP for Nexus?",
                "namespaces": ["global"],
                "top_k": 5,
                "min_score": 0.3,
            },
            headers=headers,
        )
        if resp.status_code != 200:
            fail(f"Search failed ({resp.status_code}): {resp.text}")
            results["RAG Search"] = "FAIL"
            _print_summary(results)
            return

        response_body = resp.json()
        search_results = response_body.get("results", [])
        print(f"    Returned {len(search_results)} result(s)")
        results["RAG Search"] = "PASS" if search_results else "FAIL"

        # ── Step 6: Validate content ──────────────────────────────────
        banner("Step 6: Validate Search Results")
        found_marker = False
        for i, chunk in enumerate(search_results):
            score = chunk.get("score", 0)
            text = chunk.get("text", "")
            print(f"    [{i}] score={score:.4f}  len={len(text)}  preview={text[:80]}...")
            if unique_marker in text or "10.42.0.1" in text:
                found_marker = True

        if found_marker:
            ok("RAG returned chunk containing the ingested content ✅")
            results["Validate Results"] = "PASS"
        else:
            fail("RAG did NOT return the expected content from the ingested document")
            results["Validate Results"] = "FAIL"

    _print_summary(results)


def _print_summary(results: dict[str, str]):
    print(f"\n{'=' * 60}")
    print("  RAG E2E SUMMARY")
    print(f"{'=' * 60}")
    all_pass = True
    for label, status in results.items():
        icon = "✅" if status == "PASS" else "❌"
        print(f"  {icon} {label}: {status}")
        if status != "PASS":
            all_pass = False
    print()
    if all_pass:
        print("  🎉 ALL STEPS PASSED")
    else:
        print("  ⚠️  SOME STEPS FAILED — see above for details")
    print()


if __name__ == "__main__":
    asyncio.run(run())
