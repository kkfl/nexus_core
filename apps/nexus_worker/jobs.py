import asyncio
import hashlib
import json
import os
import uuid
from datetime import datetime

import httpx
from fastapi import HTTPException
from sqlalchemy.future import select

from apps.nexus_api.routers.kb import internal_kb_search
from packages.shared import metrics as metrics_emitter
from packages.shared.db import get_db_context
from packages.shared.models import (
    Agent,
    Artifact,
    AuditEvent,
    CarrierSnapshot,
    Entity,
    EntityEvent,
    IdempotencyKey,
    KbChunk,
    KbDocument,
    KbEmbedding,
    PersonaDefault,
    PersonaVersion,
    Secret,
    StorageJob,
    Task,
    TaskLink,
    TaskRoute,
)
from packages.shared.policy import enforce_persona_policy
from packages.shared.rag.chunker import DocumentChunker
from packages.shared.rag.providers import get_embedding_provider
from packages.shared.schemas.agent_sdk import (
    AgentTaskMetadata,
    AgentTaskRequest,
    AgentTaskResponse,
    PersonaBlock,
)
from packages.shared.secrets import decrypt_secret
from packages.shared.sor import (
    SoRValidationError,
    apply_json_merge_patch,
    check_idempotency,
    validate_proposed_write,
)
from packages.shared.storage import get_storage_backend


async def _dispatch_task(task_id: int, attempt: int = 1):
    async with get_db_context() as db:
        # Load the task
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalars().first()

        if not task:
            print(f"Task {task_id} not found.")
            return

        # KI Persona resolution (REQUIRED)
        persona_version_id = task.persona_version_id
        if not persona_version_id:
            # Check persona_defaults
            # 1) scope_type='task_type' and scope_value == task.type
            pd_res = await db.execute(
                select(PersonaDefault).where(
                    PersonaDefault.scope_type == "task_type",
                    PersonaDefault.scope_value == task.type,
                    PersonaDefault.is_active is True,
                )
            )
            pd = pd_res.scalars().first()
            if not pd:
                # 2) scope_type='agent_id' and scope_value == assigned/selected agent_id
                # (handled later after agent is selected)
                pass
            else:
                persona_version_id = pd.persona_version_id

        # Load Persona
        persona_data = None
        persona_tools = None
        if persona_version_id:
            pv_res = await db.execute(
                select(PersonaVersion).where(PersonaVersion.id == persona_version_id)
            )
            pv = pv_res.scalars().first()
            if pv:
                persona_data = PersonaBlock(
                    id=str(pv.id),
                    name=pv.persona.name,
                    version=pv.version,
                    system_prompt=pv.system_prompt,
                    tools_policy=pv.tools_policy,
                )
                persona_tools = pv.tools_policy

        # Find Route
        route_res = await db.execute(
            select(TaskRoute).where(TaskRoute.task_type == task.type, TaskRoute.is_active is True)
        )
        route = route_res.scalars().first()
        req_caps = route.required_capabilities if route else []

        # KI Tools policy enforcement (REQUIRED)
        final_timeout_seconds = 30  # default
        if persona_tools is not None:
            try:
                policy_res = enforce_persona_policy(
                    task_type=task.type,
                    required_capabilities=req_caps,
                    agent_timeout_seconds=30,  # Base default, can be overridden by agent later
                    tools_policy=persona_tools,
                )
                final_timeout_seconds = policy_res.get("timeout_seconds", 30)
            except HTTPException as e:
                task.status = "failed"
                await metrics_emitter.emit(
                    db,
                    "persona_policy_violation",
                    meta={"task_id": task.id, "type": task.type, "detail": e.detail},
                )
                await db.commit()
                print(f"Task {task.id} failed: {e.detail}")
                return

        # Agent selection logic
        agent = None
        if task.assigned_agent_id:
            agent_res = await db.execute(
                select(Agent).where(Agent.id == task.assigned_agent_id, Agent.is_active is True)
            )
            agent = agent_res.scalars().first()
        else:
            # Find eligible agents
            eligibles_res = await db.execute(select(Agent).where(Agent.is_active is True))
            agents_list = eligibles_res.scalars().all()
            eligible_agents = []
            for a in agents_list:
                if a.status in ("healthy", "unknown"):
                    caps = a.capabilities or {}
                    advertised = set(caps.get("capabilities", []))
                    if set(req_caps).issubset(advertised):
                        eligible_agents.append(a)

            if route and route.preferred_agent_id:
                for a in eligible_agents:
                    if a.id == route.preferred_agent_id:
                        agent = a
                        break

            if not agent and eligible_agents:
                agent = eligible_agents[0]  # Pick first eligible

        if not agent:
            # keep queued, retry later
            print(f"No eligible agent for task {task_id}, type {task.type}. Will requeue.")
            # In complete system, enqueue with delay
            return

        # Further clamp timeout
        if final_timeout_seconds is None or (
            agent.timeout_seconds and agent.timeout_seconds < final_timeout_seconds
        ):
            final_timeout_seconds = agent.timeout_seconds

        # Update task status
        task.status = "running"
        await db.commit()

        # Step 2 Persona check
        if not persona_version_id:
            pd_res = await db.execute(
                select(PersonaDefault).where(
                    PersonaDefault.scope_type == "agent_id",
                    PersonaDefault.scope_value == str(agent.id),
                    PersonaDefault.is_active is True,
                )
            )
            pd = pd_res.scalars().first()
            if not pd:
                pd_res = await db.execute(
                    select(PersonaDefault).where(
                        PersonaDefault.scope_type == "global", PersonaDefault.is_active is True
                    )
                )
                pd = pd_res.scalars().first()
            if pd:
                pv_res = await db.execute(
                    select(PersonaVersion).where(PersonaVersion.id == pd.persona_version_id)
                )
                pv = pv_res.scalars().first()
                if pv:
                    persona_data = PersonaBlock(
                        id=str(pv.id),
                        name=pv.persona.name,
                        version=pv.version,
                        system_prompt=pv.system_prompt,
                        tools_policy=pv.tools_policy,
                    )

        # Enforce agent max_concurrency:
        # For simplicity in demo, assuming true
        running_tasks_res = await db.execute(
            select(Task).where(Task.assigned_agent_id == agent.id, Task.status == "running")
        )
        len(running_tasks_res.scalars().all())
        # The logic here is rudimentary for concurrency

        # RAG Context injection
        rag_context = None
        if route and route.needs_rag:
            query = ""
            if "query" in task.payload:
                query = task.payload["query"]
            elif "message" in task.payload:
                query = task.payload["message"]

            namespaces = route.rag_namespaces or ["global"]
            # Add persona namespace if it exists
            if persona_version_id:
                namespaces.append(f"persona:{persona_version_id}")

            top_k = route.rag_top_k or 4

            try:
                # perform internal search
                search_results = await internal_kb_search(
                    query=query,
                    namespaces=namespaces,
                    top_k=top_k,
                    db=db,
                    persona_version_id=persona_version_id,
                )

                # Fetch max context from persona policy if available
                max_context_chars = 6000
                if persona_tools and "rag" in persona_tools:
                    max_context_chars = persona_tools["rag"].get("max_context_chars", 6000)

                rag_context = []
                current_chars = 0
                for r in search_results:
                    if current_chars + len(r.text) <= max_context_chars:
                        rag_context.append(r.model_dump())
                        current_chars += len(r.text)
                    else:
                        break  # Exceeded context limit

            except ValueError as e:
                if str(e) == "persona_policy_violation":
                    task.status = "failed"
                    await db.commit()
                    print(f"Task {task.id} failed: persona_policy_violation (RAG blocked)")
                    return
                # if other errors, maybe ignore and send empty context
                print(f"RAG search error: {e}")

        req = AgentTaskRequest(
            task_id=str(task.id),
            type=task.type,
            payload=task.payload,
            persona=persona_data,
            context=rag_context,
            metadata=AgentTaskMetadata(
                attempt=attempt,
                correlation_id=str(task.id),
                requested_at=task.created_at,
                timeout_seconds=final_timeout_seconds,
            ),
        )

        # Build Authorization header (for now grab the raw text from env or skip)
        # Ideally worker would use an internal auth bypass or fetch the key
        headers = {"X-Correlation-Id": str(task.id)}

        if agent.auth_type == "api_key":
            # Decrypt outbound key
            sec_res = await db.execute(
                select(Secret).where(
                    Secret.owner_type == "agent",
                    Secret.owner_id == agent.id,
                    Secret.purpose == "agent_outbound_key",
                )
            )
            sec = sec_res.scalars().first()
            if sec:
                try:
                    decrypted_key = decrypt_secret(sec.ciphertext)
                    headers["X-Nexus-Agent-Key"] = decrypted_key
                except Exception as e:
                    print(f"Failed to decrypt agent key: {e}")
                    task.status = "failed"
                    await db.commit()
                    return

        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f"{agent.base_url}/execute",
                    json=req.model_dump(mode="json"),
                    headers=headers,
                    timeout=final_timeout_seconds,
                )
                res.raise_for_status()
                response_data = res.json()
                parsed_res = AgentTaskResponse(**response_data)

                if parsed_res.ok:
                    storage = get_storage_backend()
                    resp_bytes = json.dumps(parsed_res.result).encode("utf-8")
                    object_key = f"artifacts/tasks/{task.id}/result.json"
                    storage.put_bytes(object_key, resp_bytes, "application/json")
                    await metrics_emitter.emit(
                        db,
                        "task_succeeded",
                        meta={"task_id": task.id, "type": task.type, "agent_id": agent.id},
                    )

                    db_art = Artifact(
                        task_id=task.id,
                        kind="agent_response",
                        storage_backend="s3",
                        object_key=object_key,
                        content_type="application/json",
                        byte_size=len(resp_bytes),
                    )
                    db.add(db_art)

                    # Process Proposed Writes
                    if getattr(parsed_res, "proposed_writes", None):
                        try:
                            for pw in parsed_res.proposed_writes:
                                validate_proposed_write(pw)

                                pg_dict = pw.model_dump()
                                stored_response = await check_idempotency(
                                    db, pw.idempotency_key, "entity_write", pg_dict
                                )
                                if stored_response:
                                    continue  # Skip already applied

                                data_str = json.dumps(pg_dict, sort_keys=True)
                                req_hash = hashlib.sha256(data_str.encode()).hexdigest()

                                if pw.external_ref:
                                    res_ent = await db.execute(
                                        select(Entity).where(
                                            Entity.kind == pw.entity_kind,
                                            Entity.external_ref == pw.external_ref,
                                        )
                                    )
                                    db_ent = res_ent.scalars().first()
                                else:
                                    db_ent = None

                                before_data = dict(db_ent.data) if db_ent and db_ent.data else None

                                if db_ent:
                                    merged = apply_json_merge_patch(db_ent.data or {}, pw.patch)
                                    db_ent.data = merged
                                    db_ent.version += 1
                                    action = "update"
                                else:
                                    db_ent = Entity(
                                        id=str(uuid.uuid4()),
                                        kind=pw.entity_kind,
                                        external_ref=pw.external_ref,
                                        data=pw.patch,
                                        version=1,
                                    )
                                    db.add(db_ent)
                                    action = "create"
                                    merged = pw.patch

                                await db.flush()  # get ID if new

                                db_event = EntityEvent(
                                    id=str(uuid.uuid4()),
                                    entity_id=db_ent.id,
                                    actor_type="agent",
                                    actor_id=str(agent.id),
                                    action=action,
                                    before=before_data,
                                    after=merged,
                                    diff=pw.patch,
                                    correlation_id=str(task.id),
                                    idempotency_key=pw.idempotency_key,
                                )
                                db.add(db_event)

                                db_link = TaskLink(
                                    id=str(uuid.uuid4()),
                                    task_id=task.id,
                                    entity_id=db_ent.id,
                                    rel="updated" if action == "update" else "created",
                                )
                                db.add(db_link)

                                db.add(
                                    AuditEvent(
                                        actor_type="agent",
                                        actor_id=agent.id,
                                        action=f"entity_{action}",
                                        target_type="entity",
                                        target_id=0,
                                        meta_data={"entity_id": db_ent.id},
                                    )
                                )

                                import datetime as dt

                                db_idem = IdempotencyKey(
                                    id=str(uuid.uuid4()),
                                    key=pw.idempotency_key,
                                    scope="entity_write",
                                    request_hash=req_hash,
                                    response={"status": "applied", "entity_id": db_ent.id},
                                    expires_at=datetime.utcnow() + dt.timedelta(days=7),
                                )
                                db.add(db_idem)

                            # Process Proposed Tasks
                            if getattr(parsed_res, "proposed_tasks", None):
                                if not persona_version_id or not persona_data:
                                    raise SoRValidationError(
                                        "proposed_tasks rejected: persona inactive or missing"
                                    )

                                if "monitoring.alert_to_task" not in persona_tools.get(
                                    "allowed_capabilities", []
                                ):
                                    raise SoRValidationError(
                                        "proposed_tasks rejected: persona lacks monitoring.alert_to_task capability"
                                    )

                                for pt in parsed_res.proposed_tasks:
                                    idem_res = await db.execute(
                                        select(IdempotencyKey).where(
                                            IdempotencyKey.key == pt.idempotency_key
                                        )
                                    )
                                    if idem_res.scalars().first():
                                        continue

                                    import datetime as dt

                                    db_idem = IdempotencyKey(
                                        id=str(uuid.uuid4()),
                                        key=pt.idempotency_key,
                                        scope="task_creation",
                                        request_hash="",
                                        response={"status": "created"},
                                        expires_at=datetime.utcnow() + dt.timedelta(days=7),
                                    )
                                    db.add(db_idem)

                                    new_task = Task(
                                        type=pt.type,
                                        payload=pt.payload,
                                        requested_by_user_id=task.requested_by_user_id,
                                        requested_by_agent_id=task.requested_by_agent_id,
                                        persona_version_id=pt.persona_version_id,
                                        priority=1 if pt.priority == "high" else 0,
                                        status="queued",
                                    )
                                    db.add(new_task)
                                    await db.flush()

                                    # Link to any entities updated in this run
                                    for pw in parsed_res.proposed_writes or []:
                                        res_ent = await db.execute(
                                            select(Entity).where(
                                                Entity.kind == pw.entity_kind,
                                                Entity.external_ref == pw.external_ref,
                                            )
                                        )
                                        db_ent = res_ent.scalars().first()
                                        if db_ent:
                                            db_task_link = TaskLink(
                                                id=str(uuid.uuid4()),
                                                task_id=new_task.id,
                                                entity_id=db_ent.id,
                                                rel="alert_trigger",
                                            )
                                            db.add(db_task_link)

                            # Process Job Summary
                            if getattr(parsed_res, "job_summary", None):
                                target_id = task.payload.get("storage_target_id")
                                if target_id and parsed_res.job_summary.kind in (
                                    "copy",
                                    "lifecycle_propose",
                                    "lifecycle_apply",
                                    "delete",
                                ):
                                    new_job = StorageJob(
                                        id=str(uuid.uuid4()),
                                        storage_target_id=target_id,
                                        task_id=task.id,
                                        kind=parsed_res.job_summary.kind,
                                        status=parsed_res.job_summary.status,
                                        summary=parsed_res.job_summary.details,
                                    )
                                    db.add(new_job)
                                    db.add(
                                        AuditEvent(
                                            actor_type="agent",
                                            actor_id=agent.id,
                                            action=f"storage_job_{parsed_res.job_summary.status}",
                                            target_type="storage_job",
                                            target_id=0,
                                            meta_data={"job_id": new_job.id, "kind": new_job.kind},
                                        )
                                    )

                                carrier_target_id = task.payload.get("carrier_target_id")
                                if (
                                    carrier_target_id
                                    and parsed_res.job_summary.kind == "carrier_snapshot"
                                ):
                                    new_snapshot = CarrierSnapshot(
                                        id=str(uuid.uuid4()),
                                        carrier_target_id=carrier_target_id,
                                        task_id=task.id,
                                        status=parsed_res.job_summary.status,
                                        summary=parsed_res.job_summary.details,
                                    )
                                    db.add(new_snapshot)
                                    db.add(
                                        AuditEvent(
                                            actor_type="agent",
                                            actor_id=agent.id,
                                            action=f"carrier_snapshot_{parsed_res.job_summary.status}",
                                            target_type="carrier_snapshot",
                                            target_id=0,
                                            meta_data={"snapshot_id": new_snapshot.id},
                                        )
                                    )

                            task.status = "succeeded"
                        except SoRValidationError as e:
                            print(f"Task {task.id} failed SoR validation: {e.detail}")
                            task.status = "failed"
                        except Exception as e:
                            print(f"Task {task.id} failed to apply writes: {e}")
                            task.status = "failed"
                    else:
                        task.status = "succeeded"
                else:
                    print(f"Task {task.id} failed with agent error {parsed_res.error}")
                    task.status = "failed"

                await db.commit()

        except Exception as e:
            print(f"Failed handling task {task.id}: {str(e)}")
            task.status = "failed"
            await db.commit()


async def _embed_document(document_id: int):
    """Multi-stage RAG ingestion pipeline with event bus integration.

    Stages: extract → checksum dedup → chunk → embed → index
    Emits kb.document.* events at each stage.
    """
    import hashlib as _hashlib
    import traceback

    from packages.shared.events.api import emit_event
    from packages.shared.rag.chunker import DocumentChunker

    async def _emit(event_type: str, payload: dict):
        """Fire-and-forget event emission; never block the pipeline."""
        try:
            await emit_event(
                event_type=event_type,
                payload=payload,
                produced_by="nexus-worker",
                tenant_id="nexus",
                correlation_id=str(document_id),
            )
        except Exception:
            pass  # event emission must not break ingest

    async with get_db_context() as db:
        res = await db.execute(select(KbDocument).where(KbDocument.id == document_id))
        doc = res.scalars().first()
        if not doc:
            print(f"KbDocument {document_id} not found.")
            return

        doc.ingest_status = "processing"
        doc.error_message = None
        await db.commit()

        await _emit("kb.document.ingest_started", {
            "document_id": document_id,
            "title": doc.title,
            "content_type": doc.content_type,
        })

        try:
            # ── Stage 1: Extract ─────────────────────────────────────
            storage = get_storage_backend()
            raw_bytes = storage.get_bytes(doc.object_key)

            # Text extraction based on content_type
            if doc.content_type == "application/pdf":
                import io
                import pypdf
                pdf_file = io.BytesIO(raw_bytes)
                reader = pypdf.PdfReader(pdf_file)
                text_content = ""
                for page in reader.pages:
                    text_content += page.extract_text() + "\n"
            else:
                text_content = raw_bytes.decode("utf-8", errors="ignore")

            # Compute checksum for dedup AFTER extraction (semantic deduplication)
            content_hash = _hashlib.sha256(text_content.encode("utf-8")).hexdigest()

            # Dedup: if checksum matches and doc already indexed, skip
            if doc.checksum == content_hash and doc.ingest_status == "ready":
                print(f"Document {document_id} unchanged (checksum match), skipping.")
                await _emit("kb.document.indexed", {
                    "document_id": document_id, "skipped": True, "reason": "checksum_match",
                })
                return

            doc.checksum = content_hash

            await _emit("kb.document.text_extracted", {
                "document_id": document_id,
                "text_length": len(text_content),
            })

            # ── TEST HOOK: slow stage (for interrupt testing) ────────
            if os.environ.get("RAG_TEST_SLOW_STAGE") == "1":
                import time as _time
                print(f"[TEST] RAG_TEST_SLOW_STAGE: sleeping 30s for doc {document_id}")
                _time.sleep(30)

            # ── Stage 2: Chunk ───────────────────────────────────────
            chunker = DocumentChunker()
            chunk_infos = chunker.chunk_text_with_offsets(text_content)

            await _emit("kb.document.chunked", {
                "document_id": document_id,
                "chunk_count": len(chunk_infos),
            })

            # ── TEST HOOK: forced chunk failure ──────────────────────
            if os.environ.get("RAG_TEST_FAIL_STAGE") == "chunk":
                raise RuntimeError("TEST: forced chunk failure")

            # ── Stage 3: Embed ───────────────────────────────────────
            provider = get_embedding_provider()
            chunk_texts = [c.text for c in chunk_infos]
            embeddings = provider.embed_texts(chunk_texts)

            await _emit("kb.document.embedded", {
                "document_id": document_id,
                "chunk_count": len(embeddings),
                "model": provider.model_name,
            })

            # ── TEST HOOK: forced embed failure ──────────────────────
            if os.environ.get("RAG_TEST_FAIL_STAGE") == "embed":
                raise RuntimeError("TEST: forced embed failure")

            # ── Stage 4: Index (upsert to Postgres) ──────────────────
            # Clear old chunks and embeddings
            old_chunks_res = await db.execute(
                select(KbChunk.id).where(KbChunk.document_id == doc.id)
            )
            old_chunk_ids = [c for c in old_chunks_res.scalars().all()]
            if old_chunk_ids:
                await db.execute(
                    KbEmbedding.__table__.delete().where(KbEmbedding.chunk_id.in_(old_chunk_ids))
                )
                await db.execute(KbChunk.__table__.delete().where(KbChunk.document_id == doc.id))

            for i, (chunk_info, embedding) in enumerate(
                zip(chunk_infos, embeddings, strict=False)
            ):
                db_chunk = KbChunk(
                    document_id=doc.id,
                    chunk_index=i,
                    text_content=chunk_info.text,
                    char_count=chunk_info.char_count,
                    token_count=chunk_info.token_count,
                    start_char=chunk_info.start_char,
                    end_char=chunk_info.end_char,
                )
                db.add(db_chunk)
                await db.flush()

                db_emb = KbEmbedding(
                    chunk_id=db_chunk.id, embedding=embedding, model=provider.model_name
                )
                db.add(db_emb)

            # Inject embedding metadata into the document's meta_data JSON block
            if not doc.meta_data:
                doc.meta_data = {}
            doc.meta_data["embedding_model"] = provider.model_name
            doc.meta_data["embedding_provider"] = type(provider).__name__
            doc.meta_data["embedding_dimension"] = provider.dim

            doc.ingest_status = "ready"
            doc.version += 1
            await db.commit()

            print(f"Successfully embedded document {document_id} into {len(chunk_infos)} chunks.")
            await _emit("kb.document.indexed", {
                "document_id": document_id,
                "chunk_count": len(chunk_infos),
                "version": doc.version,
            })

        except Exception as e:
            tb = traceback.format_exc()
            error_msg = f"{type(e).__name__}: {e}"
            print(f"Failed ingesting document {document_id}: {error_msg}\n{tb}")
            doc.ingest_status = "failed"
            doc.error_message = error_msg[:2000]  # truncate for safety
            await db.commit()
            await _emit("kb.document.ingest_failed", {
                "document_id": document_id,
                "error": error_msg[:500],
            })


async def _ingest_url(url: str, source_id: int, namespace: str, title: str):
    """Fetch a URL, store raw content in MinIO, then embed."""
    from packages.shared.events.api import emit_event

    async with get_db_context() as db:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            raw_bytes = resp.content
            content_type = resp.headers.get("content-type", "text/plain").split(";")[0].strip()

            # Map common types
            if "html" in content_type:
                content_type = "text/html"
            elif "pdf" in content_type:
                content_type = "application/pdf"
            elif "plain" in content_type or "text" in content_type:
                content_type = "text/plain"

            obj_key = f"kb/{source_id}/{uuid.uuid4()}_url_fetch"
            storage = get_storage_backend()
            storage.put_bytes(obj_key, raw_bytes, content_type)

            db_doc = KbDocument(
                source_id=source_id,
                namespace=namespace,
                title=title,
                content_type=content_type,
                storage_backend="s3",
                object_key=obj_key,
                bytes_size=len(raw_bytes),
                meta_data={"source_url": url},
                ingest_status="uploaded",
            )
            db.add(db_doc)
            await db.commit()
            await db.refresh(db_doc)

            try:
                await emit_event(
                    event_type="kb.document.ingest_requested",
                    payload={"document_id": db_doc.id, "source": "url", "url": url},
                    produced_by="nexus-worker",
                    tenant_id="nexus",
                )
            except Exception:
                pass

        except Exception as e:
            print(f"URL ingest failed for {url}: {e}")
            raise

    # Now run embedding pipeline
    await _embed_document(db_doc.id)


def dispatch_task(task_id: int):
    asyncio.run(_dispatch_task(task_id))


def embed_document(document_id: int):
    asyncio.run(_embed_document(document_id))


def ingest_url(url: str, source_id: int, namespace: str, title: str):
    asyncio.run(_ingest_url(url, source_id, namespace, title))
