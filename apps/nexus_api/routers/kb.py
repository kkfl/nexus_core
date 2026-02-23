import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.nexus_api.dependencies import RequireRole, get_current_identity
from packages.shared.db import get_db
from packages.shared.models import (
    Agent,
    KbAccessLog,
    KbChunk,
    KbDocument,
    KbEmbedding,
    KbSource,
    PersonaVersion,
    User,
)
from packages.shared.queue import task_queue
from packages.shared.schemas.kb import (
    KbChunkOut,
    KbDocumentOut,
    KbDocumentTextCreate,
    KbSearchRequest,
    KbSearchResponse,
    KbSearchResult,
    KbSourceCreate,
    KbSourceOut,
)
from packages.shared.storage import get_storage_backend

router = APIRouter()


@router.post("/sources", response_model=KbSourceOut)
async def create_source(
    source_in: KbSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    db_source = KbSource(name=source_in.name, kind=source_in.kind, config=source_in.config)
    db.add(db_source)
    await db.commit()
    await db.refresh(db_source)
    return db_source


@router.get("/sources", response_model=list[KbSourceOut])
async def read_sources(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_identity: Any = Depends(get_current_identity),  # Could be user or agent
) -> Any:
    res = await db.execute(select(KbSource).offset(skip).limit(limit))
    return res.scalars().all()


@router.post("/documents/text", response_model=dict)
async def create_document_text(
    doc_in: KbDocumentTextCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    # Verify source
    res = await db.execute(select(KbSource).where(KbSource.id == doc_in.source_id))
    source = res.scalars().first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    text_bytes = doc_in.text.encode("utf-8")
    obj_key = f"kb/{doc_in.source_id}/{uuid.uuid4()}.txt"
    storage = get_storage_backend()
    storage.put_bytes(obj_key, text_bytes, "text/plain")

    db_doc = KbDocument(
        source_id=doc_in.source_id,
        namespace=doc_in.namespace,
        title=doc_in.title,
        content_type="text/plain",
        storage_backend="s3",
        object_key=obj_key,
        bytes_size=len(text_bytes),
        meta_data=doc_in.meta_data,
        ingest_status="uploaded",
    )
    db.add(db_doc)
    await db.commit()
    await db.refresh(db_doc)

    # Enqueue internal worker task
    task_queue.enqueue(
        "apps.nexus_worker.jobs.dispatch_task",  # We will reroute within worker
        task_id=db_doc.id,  # Abuse task_id for doc_id here for simple queue
        job_id=f"kb_embed_{db_doc.id}",
    )  # Actually, let's just make a specific job for kb.embed_document in the worker

    # Properly enqueue the specific kb job
    # We will define `embed_document` in jobs.py
    task_queue.enqueue(
        "apps.nexus_worker.jobs.embed_document",
        document_id=db_doc.id,
        job_id=f"kb_embed_{db_doc.id}",
    )

    return {"document_id": db_doc.id, "status": "uploaded"}


@router.post("/documents/upload", response_model=dict)
async def upload_document(
    source_id: int = Form(...),
    namespace: str = Form("global"),
    title: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    res = await db.execute(select(KbSource).where(KbSource.id == source_id))
    if not res.scalars().first():
        raise HTTPException(status_code=404, detail="Source not found")

    supported_types = ["text/plain", "text/markdown", "application/pdf"]
    content_type = file.content_type
    if content_type not in supported_types:
        # Fallback to text/plain if it's text
        if file.filename and (file.filename.endswith(".txt") or file.filename.endswith(".md")):
            content_type = "text/plain"
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported content_type: {content_type}")

    file_bytes = await file.read()
    obj_key = f"kb/{source_id}/{uuid.uuid4()}_{file.filename}"
    storage = get_storage_backend()
    storage.put_bytes(obj_key, file_bytes, content_type)

    db_doc = KbDocument(
        source_id=source_id,
        namespace=namespace,
        title=title,
        content_type=content_type,
        storage_backend="s3",
        object_key=obj_key,
        bytes_size=len(file_bytes),
        ingest_status="uploaded",
    )
    db.add(db_doc)
    await db.commit()
    await db.refresh(db_doc)

    task_queue.enqueue(
        "apps.nexus_worker.jobs.embed_document",
        document_id=db_doc.id,
        job_id=f"kb_embed_{db_doc.id}",
    )

    return {"document_id": db_doc.id, "status": "uploaded"}


@router.get("/documents", response_model=list[KbDocumentOut])
async def read_documents(
    namespace: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_identity: Any = Depends(get_current_identity),
) -> Any:
    stmt = select(KbDocument)
    if namespace:
        stmt = stmt.where(KbDocument.namespace == namespace)
    res = await db.execute(stmt.offset(skip).limit(limit))
    return res.scalars().all()


@router.get("/documents/{id}", response_model=KbDocumentOut)
async def read_document(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_identity: Any = Depends(get_current_identity),
) -> Any:
    res = await db.execute(select(KbDocument).where(KbDocument.id == id))
    doc = res.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/documents/{id}")
async def delete_document(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    res = await db.execute(select(KbDocument).where(KbDocument.id == id))
    doc = res.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.delete(
        doc
    )  # hard delete with cascade if cascading was on, but we don't have constraints set for cascade.
    # We must delete chunks and embeddings first.
    chunks_res = await db.execute(select(KbChunk.id).where(KbChunk.document_id == id))
    chunk_ids = [c for c in chunks_res.scalars().all()]
    if chunk_ids:
        await db.execute(KbEmbedding.__table__.delete().where(KbEmbedding.chunk_id.in_(chunk_ids)))
        await db.execute(KbChunk.__table__.delete().where(KbChunk.document_id == id))

    await db.delete(doc)
    await db.commit()
    return {"status": "deleted"}


@router.get("/documents/{id}/chunks", response_model=list[KbChunkOut])
async def read_chunks(
    id: int,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_identity: Any = Depends(get_current_identity),
) -> Any:
    res = await db.execute(
        select(KbChunk).where(KbChunk.document_id == id).offset(skip).limit(limit)
    )
    return res.scalars().all()


async def enforce_rag_policy(
    namespaces: list[str],
    top_k: int,
    current_identity: Any,
    db: AsyncSession,
    persona_version_id: int | None = None,
) -> dict:
    # returns {"namespaces": [...], "top_k": int}

    if isinstance(current_identity, User):
        if current_identity.role in ["admin", "operator"]:
            return {"namespaces": namespaces, "top_k": top_k}
        else:
            # Reader only gets global
            return {"namespaces": ["global"], "top_k": top_k}

    # Agent or Worker context with persona
    # Determine the persona to check
    pv_to_check = None
    if persona_version_id:
        res = await db.execute(
            select(PersonaVersion).where(PersonaVersion.id == persona_version_id)
        )
        pv_to_check = res.scalars().first()

    if pv_to_check and pv_to_check.tools_policy:
        tp = pv_to_check.tools_policy
        rag_policy = tp.get("rag", {})

        if not rag_policy.get("enabled", False):
            raise HTTPException(status_code=403, detail="rag_disabled_by_persona")

        allowed = rag_policy.get("allowed_namespaces", ["global"])
        max_top = rag_policy.get("max_top_k", 8)

        # Enforce namespaces
        valid_namespaces = []
        for ns in namespaces:
            # simple wildcard support
            if any(
                (a == "*" or a == ns or (a.endswith("*") and ns.startswith(a[:-1])))
                for a in allowed
            ):
                valid_namespaces.append(ns)

        if not valid_namespaces:
            raise HTTPException(status_code=403, detail="rag_namespace_denied")

        final_top = min(top_k, max_top)
        return {"namespaces": valid_namespaces, "top_k": final_top}

    # No persona -> safe default
    return {"namespaces": ["global"], "top_k": min(top_k, 4)}


@router.post("/search", response_model=KbSearchResponse)
async def search_kb(
    req: KbSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_identity: Any = Depends(get_current_identity),
) -> Any:
    policy = await enforce_rag_policy(req.namespaces, req.top_k, current_identity, db)

    actual_namespaces = policy["namespaces"]
    actual_top_k = policy["top_k"]

    from packages.shared.rag.providers import get_embedding_provider

    provider = get_embedding_provider()
    query_vector = provider.embed_texts([req.query])[0]

    # Audit log
    log = KbAccessLog(
        actor_type="user" if isinstance(current_identity, User) else "agent",
        actor_id=current_identity.id,
        query_text=req.query,
        namespaces=actual_namespaces,
        top_k=actual_top_k,
    )
    db.add(log)

    # pgvector ANN search
    # We join kb_embeddings and kb_chunks and kb_documents to filter namespace
    # Note: <-> is L2 distance, <=> is cosine distance. We use <=> as we created hnsw with vector_cosine_ops

    sql = text("""
        SELECT e.chunk_id, c.document_id, d.title, d.namespace, e.embedding <=> :query_embedding as distance, c.text_content
        FROM kb_embeddings e
        JOIN kb_chunks c ON c.id = e.chunk_id
        JOIN kb_documents d ON d.id = c.document_id
        WHERE d.namespace = ANY(:namespaces)
        ORDER BY distance ASC
        LIMIT :top_k
    """)

    result = await db.execute(
        sql,
        {
            "query_embedding": str(query_vector),  # pgvector parses list string
            "namespaces": actual_namespaces,
            "top_k": actual_top_k,
        },
    )

    rows = result.all()
    results = []
    for row in rows:
        results.append(
            KbSearchResult(
                chunk_id=str(row.chunk_id),
                document_id=str(row.document_id),
                title=row.title,
                namespace=row.namespace,
                score=1.0 - float(row.distance),  # Cosine similarity = 1 - distance
                text=row.text_content,
            )
        )

    await db.commit()
    return KbSearchResponse(results=results)


# Export internal search for the worker
async def internal_kb_search(
    query: str,
    namespaces: list[str],
    top_k: int,
    db: AsyncSession,
    persona_version_id: int | None = None,
) -> list[KbSearchResult]:
    # the worker acts as 'agent' context logically, but we enforce strictly via persona
    fake_identity = Agent(id=0)  # dummy for policy, we rely on persona_version_id

    try:
        policy = await enforce_rag_policy(namespaces, top_k, fake_identity, db, persona_version_id)
        actual_namespaces = policy["namespaces"]
        actual_top_k = policy["top_k"]
    except HTTPException as e:
        if e.status_code == 403:
            raise ValueError("persona_policy_violation")
        raise

    from packages.shared.rag.providers import get_embedding_provider

    provider = get_embedding_provider()
    query_vector = provider.embed_texts([query])[0]

    sql = text("""
        SELECT e.chunk_id, c.document_id, d.title, d.namespace, e.embedding <=> :query_embedding as distance, c.text_content
        FROM kb_embeddings e
        JOIN kb_chunks c ON c.id = e.chunk_id
        JOIN kb_documents d ON d.id = c.document_id
        WHERE d.namespace = ANY(:namespaces)
        ORDER BY distance ASC
        LIMIT :top_k
    """)

    result = await db.execute(
        sql,
        {
            "query_embedding": str(query_vector),
            "namespaces": actual_namespaces,
            "top_k": actual_top_k,
        },
    )

    rows = result.all()
    results = []
    for row in rows:
        results.append(
            KbSearchResult(
                chunk_id=str(row.chunk_id),
                document_id=str(row.document_id),
                title=row.title,
                namespace=row.namespace,
                score=1.0 - float(row.distance),
                text=row.text_content,
            )
        )
    return results
