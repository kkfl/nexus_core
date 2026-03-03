"""E2E Integration Check Script — runs against the live Docker stack."""

import json
import sys
import time

import httpx

API = "http://localhost:8000"
MINIO_API = "http://localhost:9000"


def section(title):
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


def main():
    client = httpx.Client(timeout=30)

    # ── Auth ──────────────────────────────────────────────────
    section("AUTH")
    r = client.post(
        f"{API}/auth/login", data={"username": "admin@nexus.local", "password": "admin_password"}
    )
    if r.status_code != 200:
        print(f"  FAIL: Login returned {r.status_code}: {r.text}")
        sys.exit(1)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"  PASS: Login OK, got JWT")

    # ── Ensure KB Source exists ─────────────────────────────────
    section("KB SOURCE")
    r = client.get(f"{API}/kb/sources", headers=headers)
    sources = r.json()
    if not sources:
        r = client.post(
            f"{API}/kb/sources", json={"name": "e2e-source", "kind": "manual"}, headers=headers
        )
        print(f"  Created source: {r.json()}")
        source_id = r.json()["id"]
    else:
        source_id = sources[0]["id"]
        print(f"  Using existing source id={source_id}")

    # ══════════════════════════════════════════════════════════
    # A) URL INGEST
    # ══════════════════════════════════════════════════════════
    section("A) URL INGEST")
    r = client.post(
        f"{API}/kb/documents/url",
        json={
            "url": "https://example.com",
            "source_id": source_id,
            "namespace": "global",
            "title": "E2E URL Test Doc",
        },
        headers=headers,
    )
    print(f"  POST /kb/documents/url -> {r.status_code}: {r.text[:200]}")

    # Give worker time to process
    print("  Waiting 8s for worker...")
    time.sleep(8)

    # Check kb_documents
    r = client.get(f"{API}/kb/documents?namespace=global", headers=headers)
    docs = r.json()
    url_doc = next((d for d in docs if d.get("title") == "E2E URL Test Doc"), None)
    if url_doc:
        print(
            f"  A1 kb_documents: id={url_doc['id']} status={url_doc['ingest_status']} checksum={url_doc.get('checksum', '?')[:16]}..."
        )
        print(
            f"     storage_backend={url_doc.get('storage_backend')} object_key={url_doc.get('object_key')}"
        )
        print(f"     version={url_doc.get('version')}")
    else:
        print(
            f"  WARN: No doc titled 'E2E URL Test Doc' found. Available: {[d['title'] for d in docs[:5]]}"
        )
        if docs:
            url_doc = docs[-1]
            print(f"  Using last doc instead: id={url_doc['id']} title={url_doc['title']}")

    if url_doc:
        doc_id = url_doc["id"]

        # Check chunks
        r = client.get(f"{API}/kb/documents/{doc_id}/chunks", headers=headers)
        chunks = r.json()
        print(f"  A3 chunks: count={len(chunks)}")
        if chunks:
            c = chunks[0]
            print(
                f"     chunk[0]: index={c.get('chunk_index')} start_char={c.get('start_char')} end_char={c.get('end_char')} chars={c.get('char_count')}"
            )

        # Check embeddings info
        r = client.get(f"{API}/kb/embeddings/info", headers=headers)
        emb_info = r.json()
        print(f"  A4 embeddings/info: {json.dumps(emb_info, indent=2)}")

        # Search with citations
        r = client.post(
            f"{API}/kb/search",
            json={"query": "example domain", "top_k": 3, "namespaces": ["global"]},
            headers=headers,
        )
        search = r.json()
        results = search.get("results", [])
        print(f"  A5 search: {len(results)} results")
        for sr in results[:2]:
            print(
                f"     doc_id={sr.get('document_id')} chunk_idx={sr.get('chunk_index')} start={sr.get('start_char')} end={sr.get('end_char')} score={sr.get('score', '?')}"
            )

    # ══════════════════════════════════════════════════════════
    # A6) Event bus check (bus_events in Postgres)
    # ══════════════════════════════════════════════════════════
    section("A6) EVENT BUS")
    r = client.get(f"{API}/events?event_type=kb.document.indexed&limit=5", headers=headers)
    ev_data = r.json()
    print(f"  bus_events (kb.document.indexed): count={ev_data.get('count', 0)}")
    for ev in ev_data.get("events", [])[:2]:
        print(
            f"    id={ev.get('id', '?')[:12]}... type={ev.get('event_type')} producer={ev.get('produced_by')}"
        )

    # Redis streams
    r = client.get(f"{API}/events/streams", headers=headers)
    streams = r.json()
    print(f"  Redis streams: {json.dumps(streams, indent=2)[:400]}")

    # DLQ
    r = client.get(f"{API}/events/dlq", headers=headers)
    dlq = r.json()
    print(f"  DLQ entries: count={dlq.get('count', 0)}")

    # ══════════════════════════════════════════════════════════
    # B) EMAIL INGEST
    # ══════════════════════════════════════════════════════════
    section("B) EMAIL INGEST")
    r = client.post(
        f"{API}/kb/documents/email-ingest",
        json={
            "source_id": source_id,
            "namespace": "global",
            "subject": "E2E Test Email",
            "body_text": "This is a test email body. It discusses DNS configuration and how the event bus works with Redis streams for real-time notifications.",
            "sender": "test@example.com",
            "message_id": "e2e-test-001",
        },
        headers=headers,
    )
    print(f"  POST /kb/documents/email-ingest -> {r.status_code}: {r.text[:200]}")

    if r.status_code == 200:
        email_doc_id = r.json().get("document_id")
        print(f"  Waiting 8s for worker...")
        time.sleep(8)

        r = client.get(f"{API}/kb/documents/{email_doc_id}", headers=headers)
        if r.status_code == 200:
            ed = r.json()
            print(
                f"  B doc: id={ed['id']} status={ed['ingest_status']} storage={ed.get('storage_backend')} key={ed.get('object_key')}"
            )
            print(
                f"     checksum={ed.get('checksum', '?')[:16]}... meta={json.dumps(ed.get('meta_data', {}))[:200]}"
            )

            r = client.get(f"{API}/kb/documents/{email_doc_id}/chunks", headers=headers)
            email_chunks = r.json()
            print(f"  B chunks: count={len(email_chunks)}")

    # ══════════════════════════════════════════════════════════
    # D) EVENT BUS HEALTH (expanded)
    # ══════════════════════════════════════════════════════════
    section("D) EVENT BUS HEALTH")
    r = client.get(f"{API}/events?produced_by=nexus-worker&limit=10", headers=headers)
    worker_events = r.json()
    print(f"  Worker-produced events: count={worker_events.get('count', 0)}")
    types_seen = set()
    for ev in worker_events.get("events", []):
        types_seen.add(ev.get("event_type"))
    print(f"  Event types seen: {sorted(types_seen)}")

    # ══════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════
    section("SUMMARY")
    print("  Check the output above for PASS/FAIL per item.")
    print("  Done.")


if __name__ == "__main__":
    main()
