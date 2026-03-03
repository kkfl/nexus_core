"""Worker startup — recover documents stuck in 'processing' after a crash."""

import asyncio

from sqlalchemy.future import select

from packages.shared.db import get_db_context
from packages.shared.models.core import KbDocument
from packages.shared.queue import task_queue


async def recover_stuck_documents():
    """Find docs stuck in 'processing' and re-enqueue them."""
    async with get_db_context() as db:
        res = await db.execute(select(KbDocument).where(KbDocument.ingest_status == "processing"))
        stuck = res.scalars().all()

        if not stuck:
            print("[startup] No stuck documents found.")
            return

        print(f"[startup] Found {len(stuck)} document(s) stuck in 'processing', recovering...")

        for doc in stuck:
            doc.ingest_status = "uploaded"
            doc.error_message = "Recovered after worker restart (was stuck in processing)"
            await db.flush()

            task_queue.enqueue(
                "apps.nexus_worker.jobs.embed_document",
                document_id=doc.id,
                job_id=f"kb_recover_{doc.id}",
            )
            print(f"  [startup] Re-enqueued doc id={doc.id} title='{doc.title}'")

        await db.commit()
        print(f"[startup] Recovery complete — {len(stuck)} doc(s) re-queued.")


def main():
    asyncio.run(recover_stuck_documents())


if __name__ == "__main__":
    main()
