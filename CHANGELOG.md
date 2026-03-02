# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-03-01

### Added

#### Event Bus (Redis Streams + Postgres)
- Redis Streams-backed event bus with at-least-once delivery, consumer groups, and DLQ.
- Persistent event store in `bus_events` Postgres table (Alembic migration 024).
- Admin endpoints: `/events/streams`, `/events`, `/events/dlq`, `/events/replay`.

#### RAG Ingestion Pipeline V1
- Full KB ingestion pipeline: URL, text, email, and reingest support.
- Chunking, embedding (BAAI/bge-small-en-v1.5), and vector search with cosine similarity.
- Worker reliability: retry on mid-ingest interruption, idempotent re-ingestion.
- Repo docs seeding script (`scripts/ingest_repo_docs.py`) with safe doc selection.
- Evaluation harness (`scripts/eval_runner.py`) with golden set and PASS/FAIL reporting.

#### Ask Nexus V1
- `POST /kb/ask` endpoint: retrieves top_k chunks with citations from the knowledge base.
- Citation-ready response payload: document_id, title, chunk_index, score, excerpt.
- Portal UI page (`/kb/ask`): question input, answer display, expandable citations.

#### Ask Nexus Production Hardening
- RBAC enforcement via `RequireRole(["admin", "operator", "reader"])`.
- Redis-based rate limiting (30 req / 5 min per user, configurable via env vars).
- Pydantic input validation (query 3-2000 chars, top_k clamped 1-10).
- Structured logging with `structlog` (correlation_id, user_id, timing metrics).
- Event persistence: ask.requested, ask.retrieved, ask.responded, ask.failed events to bus_events.
- Feedback loop: `POST /kb/ask/feedback`, `ask_feedback` table (Alembic migration 026), portal thumbs up/down UI.
- Namespace isolation: reader role silently scoped to `["global"]`; admin/operator pass-through.

#### Smoke Check
- Post-deployment health verification script (`scripts/smoke_check.py`).
- 7 checks: API health, KB ingest, ingest poll, Ask Nexus + citations, bus_events, feedback, rate limiter.
- Idempotent, env-configurable, CI-safe (exit code 0/1).

## [0.1.0] - 2026-02-21

### Added
- Initial V1 release of Nexus Core.
- Central API server (`nexus-api`) handling users, authentication, schemas, and task dispatching.
- Async `nexus-worker` utilizing Redis Queue (RQ) for autonomous agent proxying.
- Canonical System of Record (Entities & Audit trails) powered by Postgres & SQLAlchemy.
- Secure Credentials Vault using AES-GCM envelope encryption.
- Robust Persona limits (Tools Policy, Deny Task Types) enforced proactively.
- Complete ecosystem of autonomous agents (Carrier, Monitoring, Storage, PBX).
- Nexus Portal React-based Admin UI.
- Local developer Docker Compose environments.
