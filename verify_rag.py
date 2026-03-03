import asyncio
import os
import uuid
import httpx
from sqlalchemy.future import select

# Setup python path to allow importing nexus_core modules
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from packages.shared.db import get_db_context
from packages.shared.models.core import KbSource, KbDocument, KbEmbedding
from packages.shared.storage import get_storage_backend


async def verify():
    # 1. Create a source directly in DB
    async with get_db_context() as db:
        source_name = f"test-source-{uuid.uuid4().hex[:6]}"
        db_source = KbSource(name=source_name, kind="web")
        db.add(db_source)
        await db.commit()
        await db.refresh(db_source)
        source_id = db_source.id
        print(f"Created KbSource with ID: {source_id}")

    # 2. Trigger URL Ingest
    url_req = {
        "url": "https://example.com",
        "source_id": source_id,
        "namespace": "global",
        "title": "Example Domain",
    }

    # 3. Trigger Email Ingest
    email_req = {
        "source_id": source_id,
        "namespace": "global",
        "subject": "Test Email",
        "body_text": "This is a test email body for ingestion verification.",
        "sender": "example@example.com",
        "message_id": "12345",
    }

    print("\n--- Triggering Ingest API ---")
    async with httpx.AsyncClient(base_url="http://localhost:8000/v1") as ac:
        try:
            headers = {"X-Service-ID": "admin", "X-Agent-Key": "admin-key"}
            res_url = await ac.post("/kb/documents/url", json=url_req, headers=headers)
            print("URL Ingest API Response:", res_url.status_code, res_url.text)

            res_email = await ac.post("/kb/documents/email-ingest", json=email_req, headers=headers)
            print("Email Ingest API Response:", res_email.status_code, res_email.text)
        except Exception as e:
            print(f"Failed to call API (is it running?): {e}")
            print("Will attempt direct worker call if possible...")
            from apps.nexus_worker.jobs import _ingest_url
            from apps.nexus_api.routers.kb import ingest_from_email, KbEmailIngestRequest

            await _ingest_url("https://example.com", source_id, "global", "Example Domain")

            # Wait a few seconds for queue/worker if it was running
            await asyncio.sleep(2)

    # 4. Wait for processing
    print("\nWaiting 5 seconds for processing...")
    await asyncio.sleep(5)

    # 5. Verify DB and MinIO
    print("\n--- Verification Results ---")
    storage = get_storage_backend()

    async with get_db_context() as db:
        res = await db.execute(select(KbDocument).where(KbDocument.source_id == source_id))
        docs = res.scalars().all()
        print(f"Found {len(docs)} documents in DB for source {source_id}:")
        for doc in docs:
            print(f"  Doc ID: {doc.id} | Title: {doc.title} | Status: {doc.ingest_status}")
            print(
                f"  Storage: {doc.storage_backend} | Key: {doc.object_key} | Content-Type: {doc.content_type}"
            )
            print(f"  Checksum: {doc.checksum}")

            # Verify MinIO
            try:
                raw_bytes = storage.get_bytes(doc.object_key)
                print(
                    f"  [PASS] Successfully retrieved {len(raw_bytes)} bytes from MinIO for {doc.object_key}"
                )
            except Exception as e:
                print(f"  [FAIL] Could not retrieve from MinIO: {e}")

            # Check embeddings metadata
            res_emb = await db.execute(
                select(KbEmbedding)
                .join(KbEmbedding.chunk_id)
                .where(
                    KbEmbedding.chunk_id.in_(
                        select(KbEmbedding.chunk_id).where(
                            KbEmbedding.chunk_id.in_(
                                # Hacky join, let's just do a simpler search
                                []
                            )
                        )
                    )
                )
            )  # skipping complex join, just check embeddings table total

        # Check overall embeddings
        from packages.shared.models.core import KbChunk

        for doc in docs:
            res_chunks = await db.execute(select(KbChunk).where(KbChunk.document_id == doc.id))
            chunks = res_chunks.scalars().all()
            print(f"  Chunks found: {len(chunks)} for Doc {doc.id}")
            for c in chunks:
                res_e = await db.execute(select(KbEmbedding).where(KbEmbedding.chunk_id == c.id))
                emb = res_e.scalars().first()
                if emb:
                    print(
                        f"    Embedding: model='{emb.model}', dimension=(hardcoded 384 in schema)"
                    )


if __name__ == "__main__":
    asyncio.run(verify())
