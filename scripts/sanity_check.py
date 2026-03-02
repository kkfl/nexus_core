"""Sanity check: ingest test docs and verify MinIO + Postgres."""
import httpx
import json

API = "http://localhost:8000"

# Login
r = httpx.post(f"{API}/auth/login", json={"username": "admin", "password": "admin123"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}"}
print("✓ Logged in")

# Create source if needed
r = httpx.get(f"{API}/kb/sources", headers=h)
sources = r.json()
src_id = None
for s in sources:
    if s["name"] == "sanity-test":
        src_id = s["id"]
        break
if not src_id:
    r = httpx.post(f"{API}/kb/sources", json={"name": "sanity-test", "kind": "manual"}, headers=h)
    src_id = r.json()["id"]
    print(f"✓ Created source: {src_id}")
else:
    print(f"✓ Using existing source: {src_id}")

# Ingest text document
r = httpx.post(f"{API}/kb/documents/text", json={
    "source_id": src_id,
    "namespace": "global",
    "title": "Sanity Check Test Doc",
    "text": "Nexus is a multi-agent orchestration platform. It manages DNS, email, and knowledge base agents through a central API with RBAC, event bus, and RAG capabilities.",
}, headers=h, timeout=10)
print(f"✓ Text ingest: {r.json()}")
text_doc_id = r.json().get("document_id")

# Ingest email body
r2 = httpx.post(f"{API}/kb/documents/email-ingest", json={
    "source_id": src_id,
    "namespace": "global",
    "subject": "Test Email Subject",
    "body_text": "This is a test email body for RAG ingestion verification.",
    "sender": "test@example.com",
    "message_id": "msg-sanity-001",
}, headers=h, timeout=10)
print(f"✓ Email ingest: {r2.json()}")
email_doc_id = r2.json().get("document_id")

# Wait a moment for worker, then check
import time
time.sleep(3)

# List last documents
r3 = httpx.get(f"{API}/kb/documents?limit=100", headers=h)
docs = r3.json()
print(f"\n=== Last 5 Documents ===")
for d in docs[-5:]:
    print(f"  id={d['id']} title={d['title'][:30]} status={d['ingest_status']}"
          f" backend={d['storage_backend']} key={d['object_key'][:40]}..."
          f" checksum={str(d.get('checksum','?'))[:16]}... ver={d.get('version',1)}")

# Check embedding metadata
from sqlalchemy import create_engine, text
import os
db_url = os.environ.get("DATABASE_URL", "postgresql://nexus:nexus@localhost:5432/nexus_core")
engine = create_engine(db_url.replace("+asyncpg", ""))
with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT DISTINCT model, COUNT(*) as cnt FROM kb_embeddings GROUP BY model"
    )).fetchall()
    print(f"\n=== Embedding Models in DB ===")
    for row in rows:
        print(f"  model={row[0]}, embeddings_count={row[1]}")

    # Check dimension from actual vector
    row = conn.execute(text(
        "SELECT array_length(embedding::real[], 1) as dim FROM kb_embeddings LIMIT 1"
    )).fetchone()
    if row:
        print(f"  vector_dimension={row[0]}")

print("\n✓ Sanity check complete")
