import hashlib
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.nexus_api.dependencies import RequireModuleAccess, RequireRole, get_current_identity
from packages.shared.db import get_db
from packages.shared.models import (
    Agent,
    AskFeedback,
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
    AskFeedbackRequest,
    AskNexusCitation,
    AskNexusRequest,
    AskNexusResponse,
    KbChunkOut,
    KbDocumentOut,
    KbDocumentTextCreate,
    KbEmailIngestRequest,
    KbSearchRequest,
    KbSearchResponse,
    KbSearchResult,
    KbSourceCreate,
    KbSourceOut,
    KbUrlIngestRequest,
)
from packages.shared.storage import get_storage_backend

router = APIRouter()


@router.post("/sources", response_model=KbSourceOut)
async def create_source(
    source_in: KbSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireModuleAccess("knowledge_base", "manage")),
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
    current_user: User = Depends(RequireModuleAccess("knowledge_base", "manage")),
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

    content_hash = hashlib.sha256(text_bytes).hexdigest()

    db_doc = KbDocument(
        source_id=doc_in.source_id,
        namespace=doc_in.namespace,
        title=doc_in.title,
        content_type="text/plain",
        storage_backend="s3",
        object_key=obj_key,
        bytes_size=len(text_bytes),
        checksum=content_hash,
        meta_data=doc_in.meta_data,
        ingest_status="uploaded",
    )
    db.add(db_doc)
    await db.commit()
    await db.refresh(db_doc)

    # Enqueue embedding pipeline
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
    current_user: User = Depends(RequireModuleAccess("knowledge_base", "manage")),
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

    content_hash = hashlib.sha256(file_bytes).hexdigest()

    db_doc = KbDocument(
        source_id=source_id,
        namespace=namespace,
        title=title,
        content_type=content_type,
        storage_backend="s3",
        object_key=obj_key,
        bytes_size=len(file_bytes),
        checksum=content_hash,
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


# ── URL Ingest ────────────────────────────────────────────────────────


@router.post("/documents/url", response_model=dict)
async def ingest_from_url(
    req: KbUrlIngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireModuleAccess("knowledge_base", "manage")),
) -> Any:
    """Fetch a URL, store raw content, and enqueue for embedding."""
    res = await db.execute(select(KbSource).where(KbSource.id == req.source_id))
    if not res.scalars().first():
        raise HTTPException(status_code=404, detail="Source not found")

    task_queue.enqueue(
        "apps.nexus_worker.jobs.ingest_url",
        url=req.url,
        source_id=req.source_id,
        namespace=req.namespace,
        title=req.title,
        job_id=f"kb_url_{uuid.uuid4().hex[:8]}",
    )

    return {"status": "queued", "message": f"URL ingest queued for: {req.url}"}


# ── Email Ingest Hook ────────────────────────────────────────────────


@router.post("/documents/email-ingest", response_model=dict)
async def ingest_from_email(
    req: KbEmailIngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireModuleAccess("knowledge_base", "manage")),
) -> Any:
    """Ingest email body text as a KB document."""
    res = await db.execute(select(KbSource).where(KbSource.id == req.source_id))
    if not res.scalars().first():
        raise HTTPException(status_code=404, detail="Source not found")

    text_bytes = req.body_text.encode("utf-8")
    obj_key = f"kb/{req.source_id}/{uuid.uuid4()}_email.txt"
    storage = get_storage_backend()
    storage.put_bytes(obj_key, text_bytes, "text/plain")

    content_hash = hashlib.sha256(text_bytes).hexdigest()

    db_doc = KbDocument(
        source_id=req.source_id,
        namespace=req.namespace,
        title=req.subject,
        content_type="text/plain",
        storage_backend="s3",
        object_key=obj_key,
        bytes_size=len(text_bytes),
        checksum=content_hash,
        meta_data={
            "source_type": "email",
            "sender": req.sender,
            "message_id": req.message_id,
        },
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


# ── Re-ingest ────────────────────────────────────────────────────────


@router.post("/documents/{id}/reingest", response_model=dict)
async def reingest_document(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireModuleAccess("knowledge_base", "manage")),
) -> Any:
    """Re-run the ingestion pipeline for an existing document."""
    res = await db.execute(select(KbDocument).where(KbDocument.id == id))
    doc = res.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Reset status to trigger full re-embed (clear checksum to bypass dedup)
    doc.ingest_status = "uploaded"
    doc.error_message = None
    doc.checksum = None
    await db.commit()

    task_queue.enqueue(
        "apps.nexus_worker.jobs.embed_document",
        document_id=doc.id,
        job_id=f"kb_reingest_{doc.id}_{uuid.uuid4().hex[:6]}",
    )

    return {"document_id": doc.id, "status": "reingesting"}


# ── CRUD ─────────────────────────────────────────────────────────────


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
    current_user: User = Depends(RequireModuleAccess("knowledge_base", "manage")),
) -> Any:
    res = await db.execute(select(KbDocument).where(KbDocument.id == id))
    doc = res.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete embeddings and chunks first (no cascade)
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


# ── RAG Policy + Search ──────────────────────────────────────────────


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

    # pgvector ANN search with citation fields
    # NOTE: query_embedding is embedded as a SQL string literal because
    # asyncpg cannot cast bound parameters to pgvector's vector type.
    # The vector is generated server-side by fastembed, so this is safe.
    query_embedding_str = str(query_vector)
    sql = text(f"""
        SELECT e.chunk_id, c.document_id, d.title, d.namespace,
               c.chunk_index, c.start_char, c.end_char,
               e.embedding <=> '{query_embedding_str}'::vector as distance, c.text_content
        FROM kb_embeddings e
        JOIN kb_chunks c ON c.id = e.chunk_id
        JOIN kb_documents d ON d.id = c.document_id
        WHERE d.namespace = ANY(:namespaces)
          AND d.ingest_status = 'ready'
        ORDER BY distance ASC
        LIMIT :top_k
    """)

    result = await db.execute(
        sql,
        {
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
                chunk_index=row.chunk_index,
                start_char=row.start_char,
                end_char=row.end_char,
                score=1.0 - float(row.distance),
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
    fake_identity = Agent(id=0)

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

    query_embedding_str = str(query_vector)
    sql = text(f"""
        SELECT e.chunk_id, c.document_id, d.title, d.namespace,
               c.chunk_index, c.start_char, c.end_char,
               e.embedding <=> '{query_embedding_str}'::vector as distance, c.text_content
        FROM kb_embeddings e
        JOIN kb_chunks c ON c.id = e.chunk_id
        JOIN kb_documents d ON d.id = c.document_id
        WHERE d.namespace = ANY(:namespaces)
          AND d.ingest_status = 'ready'
        ORDER BY distance ASC
        LIMIT :top_k
    """)

    result = await db.execute(
        sql,
        {
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
                chunk_index=row.chunk_index,
                start_char=row.start_char,
                end_char=row.end_char,
                score=1.0 - float(row.distance),
                text=row.text_content,
            )
        )
    return results


# ── Embedding Metadata Info ──────────────────────────────────────────


@router.get("/embeddings/info")
async def embeddings_info(
    db: AsyncSession = Depends(get_db),
    current_identity: Any = Depends(get_current_identity),
) -> dict:
    """Report current embedding model, dimensions, and counts for ops verification."""
    from sqlalchemy import func as sa_func

    from packages.shared.rag.providers import get_embedding_provider

    provider = get_embedding_provider()

    # Count embeddings and chunks
    emb_count = (await db.execute(select(sa_func.count()).select_from(KbEmbedding))).scalar() or 0

    chunk_count = (await db.execute(select(sa_func.count()).select_from(KbChunk))).scalar() or 0

    doc_count = (await db.execute(select(sa_func.count()).select_from(KbDocument))).scalar() or 0

    # Get distinct models actually used in stored embeddings
    models_query = await db.execute(
        select(KbEmbedding.model, sa_func.count()).group_by(KbEmbedding.model)
    )
    stored_models = {row[0]: row[1] for row in models_query.all()}

    return {
        "current_provider": {
            "model_name": provider.model_name,
            "dimension": provider.dim,
            "provider_class": type(provider).__name__,
        },
        "stored_embeddings": {
            "total_embeddings": emb_count,
            "total_chunks": chunk_count,
            "total_documents": doc_count,
            "models_in_use": stored_models,
        },
    }


# ── Ask Nexus (hardened) ─────────────────────────────────────────────

import os
import time

import structlog

ask_logger = structlog.get_logger("ask_nexus")

ASK_RATE_LIMIT = int(os.environ.get("ASK_RATE_LIMIT", "30"))
ASK_RATE_WINDOW = int(os.environ.get("ASK_RATE_WINDOW", "300"))


async def _check_rate_limit(user_id: int) -> bool:
    """Return True if rate limit exceeded. Uses Redis INCR + EXPIRE."""
    import redis.asyncio as aioredis

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    redis = aioredis.from_url(redis_url, decode_responses=True)
    try:
        key = f"ask_ratelimit:{user_id}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, ASK_RATE_WINDOW)
        return count > ASK_RATE_LIMIT
    finally:
        await redis.close()


@router.post("/ask", response_model=AskNexusResponse)
async def ask_nexus(
    req: AskNexusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireModuleAccess("knowledge_base", "read")),
) -> Any:
    """Ask a question and get a citation-ready response from the knowledge base."""
    from packages.shared.events import emit_event
    from packages.shared.rag.providers import get_embedding_provider

    correlation_id = str(uuid.uuid4())
    t_start = time.monotonic()

    # ── Rate limiting ────────────────────────────────────────────────
    if await _check_rate_limit(current_user.id):
        await emit_event(
            event_type="ask.failed",
            payload={"reason": "rate_limited", "user_id": current_user.id},
            produced_by="nexus-api",
            correlation_id=correlation_id,
            db=db,
        )
        await db.commit()
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

    # ── Emit ask.requested (persisted) ───────────────────────────────
    await emit_event(
        event_type="ask.requested",
        payload={"query": req.query[:100], "top_k": req.top_k, "namespaces": req.namespaces},
        produced_by="nexus-api",
        correlation_id=correlation_id,
        actor_type="user",
        actor_id=str(current_user.id),
        db=db,
    )

    try:
        # ── Namespace scoping via enforce_rag_policy ─────────────────
        policy = await enforce_rag_policy(req.namespaces, req.top_k, current_user, db)
        actual_namespaces = policy["namespaces"]
        actual_top_k = policy["top_k"]

        provider = get_embedding_provider()
        query_vector = provider.embed_texts([req.query])[0]

        # Audit log
        log = KbAccessLog(
            actor_type="user",
            actor_id=current_user.id,
            query_text=req.query,
            namespaces=actual_namespaces,
            top_k=actual_top_k,
        )
        db.add(log)

        t_retrieve_start = time.monotonic()
        query_embedding_str = str(query_vector)
        sql = text(f"""
            SELECT e.chunk_id, c.document_id, d.title, d.namespace,
                   c.chunk_index, c.start_char, c.end_char,
                   e.embedding <=> '{query_embedding_str}'::vector as distance, c.text_content
            FROM kb_embeddings e
            JOIN kb_chunks c ON c.id = e.chunk_id
            JOIN kb_documents d ON d.id = c.document_id
            WHERE d.namespace = ANY(:namespaces)
              AND d.ingest_status = 'ready'
            ORDER BY distance ASC
            LIMIT :top_k
        """)
        result = await db.execute(sql, {"namespaces": actual_namespaces, "top_k": actual_top_k})
        rows = result.all()
        retrieve_ms = round((time.monotonic() - t_retrieve_start) * 1000, 1)

        # ── Emit ask.retrieved (persisted) ───────────────────────────
        await emit_event(
            event_type="ask.retrieved",
            payload={
                "chunk_count": len(rows),
                "namespaces": actual_namespaces,
                "retrieve_ms": retrieve_ms,
            },
            produced_by="nexus-api",
            correlation_id=correlation_id,
            db=db,
        )

        # Build citations
        citations = []
        for row in rows:
            score = 1.0 - float(row.distance)
            excerpt = row.text_content[:500] if row.text_content else ""
            citations.append(
                AskNexusCitation(
                    document_id=str(row.document_id),
                    title=row.title,
                    chunk_id=str(row.chunk_id),
                    chunk_index=row.chunk_index,
                    start_char=row.start_char,
                    end_char=row.end_char,
                    score=score,
                    excerpt=excerpt,
                )
            )

        # ── Answer synthesis (LLM if available, else V1 excerpts) ────
        from packages.shared.rag.llm import build_rag_prompt, get_llm_provider

        llm = get_llm_provider()
        if citations and llm:
            try:
                citation_dicts = [
                    {"title": c.title, "excerpt": c.excerpt, "score": c.score} for c in citations
                ]
                system_prompt = build_rag_prompt(citation_dicts)
                answer = llm.complete(system_prompt, req.query)
                ask_logger.info(
                    "ask_llm_synthesized",
                    correlation_id=correlation_id,
                    model=llm.model_name,
                    citation_count=len(citations),
                )
            except Exception as llm_exc:
                # LLM failed — fall back to V1 excerpt mode
                ask_logger.warning(
                    "ask_llm_fallback",
                    correlation_id=correlation_id,
                    error=str(llm_exc)[:200],
                )
                answer = (
                    f"Based on {len(citations)} relevant document(s) from the knowledge base:\n\n"
                    + "\n\n---\n\n".join(
                        f"**{c.title}** (score: {c.score:.0%})\n{c.excerpt[:300]}..."
                        if len(c.excerpt) > 300
                        else f"**{c.title}** (score: {c.score:.0%})\n{c.excerpt}"
                        for c in citations[:3]
                    )
                )
        elif citations:
            # No LLM configured — V1 excerpt fallback
            answer = (
                f"Based on {len(citations)} relevant document(s) from the knowledge base:\n\n"
                + "\n\n---\n\n".join(
                    f"**{c.title}** (score: {c.score:.0%})\n{c.excerpt[:300]}..."
                    if len(c.excerpt) > 300
                    else f"**{c.title}** (score: {c.score:.0%})\n{c.excerpt}"
                    for c in citations[:3]
                )
            )
        else:
            answer = "No relevant documents found for your question. Try broadening your search or ingesting more documentation."

        await db.commit()
        total_ms = round((time.monotonic() - t_start) * 1000, 1)

        response = AskNexusResponse(
            correlation_id=correlation_id,
            answer=answer,
            citations=citations,
            retrieval_debug={
                "top_k": actual_top_k,
                "namespaces": actual_namespaces,
                "model": provider.model_name,
                "provider": type(provider).__name__,
                "chunks_returned": len(citations),
                "retrieve_ms": retrieve_ms,
                "total_ms": total_ms,
            },
        )

        # ── Structured log ───────────────────────────────────────────
        ask_logger.info(
            "ask_responded",
            correlation_id=correlation_id,
            user_id=current_user.id,
            namespaces=actual_namespaces,
            retrieve_ms=retrieve_ms,
            total_ms=total_ms,
            result_count=len(citations),
        )

        # ── Emit ask.responded (persisted) ───────────────────────────
        await emit_event(
            event_type="ask.responded",
            payload={
                "citation_count": len(citations),
                "answer_length": len(answer),
                "total_ms": total_ms,
            },
            produced_by="nexus-api",
            correlation_id=correlation_id,
            db=db,
        )

        return response

    except HTTPException:
        raise  # Re-raise 403, 429, etc. without wrapping
    except Exception as e:
        total_ms = round((time.monotonic() - t_start) * 1000, 1)
        ask_logger.error(
            "ask_failed",
            correlation_id=correlation_id,
            user_id=current_user.id,
            error=str(e)[:200],
            total_ms=total_ms,
        )
        await emit_event(
            event_type="ask.failed",
            payload={"error": str(e)[:200], "reason": "internal_error"},
            produced_by="nexus-api",
            correlation_id=correlation_id,
            db=db,
        )
        raise HTTPException(status_code=500, detail=f"Ask failed: {str(e)[:200]}")


# ── Ask Feedback ─────────────────────────────────────────────────────


@router.post("/ask/feedback")
async def submit_ask_feedback(
    req: AskFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireModuleAccess("knowledge_base", "read")),
) -> dict:
    """Submit feedback on an Ask Nexus response."""
    from packages.shared.events import emit_event

    feedback = AskFeedback(
        correlation_id=req.correlation_id,
        user_id=current_user.id,
        rating=req.rating,
        note=req.note,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    await emit_event(
        event_type="ask.feedback_received",
        payload={
            "correlation_id": req.correlation_id,
            "rating": req.rating,
            "feedback_id": feedback.id,
        },
        produced_by="nexus-api",
        correlation_id=req.correlation_id,
        actor_type="user",
        actor_id=str(current_user.id),
        db=db,
    )

    return {"status": "ok", "feedback_id": feedback.id}
