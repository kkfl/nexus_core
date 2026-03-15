# Changelog

All notable changes to Nexus Core are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.5.0] — 2026-03-15

### Added
- Centralized theme system (`theme.ts`) with `NexusTokens` design tokens
- Dark/light mode toggle with `themeStore.ts` (zustand, localStorage-persisted)
- Sun/moon toggle button in portal header

### Changed
- Migrated all 25 portal pages from hardcoded `MN.*` color tokens to `getTokens(mode)` pattern
- `AdminLayout.tsx` uses `ConfigProvider` with `getAntTheme(mode)`
- `App.css` stripped to minimal overrides (theming now in TypeScript)

### Fixed
- Backend formatting (twilio adapter, redaction module, notification runner)

---

## [0.4.0] — 2026-03-14

### Added
- Ask Nexus LLM synthesis layer (`packages/shared/rag/llm.py`)
- `OpenAILLMProvider` (gpt-4o-mini) with graceful fallback to V1 excerpts
- KB seed script (`scripts/seed_external_docs.py`) — 11 curated docs (Vultr, Cloudflare, iRedMail, Nexus)
- `external-docs` namespace for third-party documentation

### Changed
- `/kb/ask` endpoint uses LLM for coherent answer synthesis instead of raw excerpt concatenation
- `AskNexus.tsx` updated with new placeholder and external-docs namespace

---

## [0.3.0] — 2026-03-13

### Added
- User Management page and API (`/settings/users`)
- Storage Targets redesign with MinIO S3-compatible target management

---

## [0.2.1] — 2026-03-12

### Fixed
- Alembic migration chain repair (025-027)
- CI lint fixes: ruff formatting, eslint, react-hooks/purity rules

---

## [0.2.0] — 2026-03-07

### Added
- Dashboard Command Center redesign with system activity log
- Transaction heartbeat monitoring for micro-agents
- Complete production configs for all services (Docker, nginx proxy)

---

## [0.1.7] — 2026-03-04

### Added
- Batch mailbox stats: single SSH call + Postgres cache + background refresh

### Fixed
- `collected_at` datetime parse + timezone import

---

## [0.1.6] — 2026-03-03

### Added
- Email Admin v2: stats dashboard, drill-down inbox, server tiles

---

## [0.1.5] — 2026-03-02

### Fixed
- Notifications: STARTTLS cert validation for internal mail servers
- Notifications: STARTTLS fix for port 587 + email smoke test
- Portal auth + proxy email-agent route

---

## [0.1.4] — 2026-03-01

### Fixed
- Registry: idempotent seeding + `auth_secret_alias` for all agents
- CI python-lint (ruff format + ruff check)

---

## [0.1.3] — 2026-02-28

### Added
- Portal Secrets UI + break-glass reveal (120s auto-expiry)
- DNSMadeEasy live write smoke test

### Fixed
- CI failures: ruff formatting + eslint declaration order
- CI: unused imports + async setState in effect

---

## [0.1.2] — 2026-02-26

### Fixed
- Dockerfile path fixes for repo-root build context (nexus_portal)
- Hatchling wheel package config for monorepo build
- Dev extras install so pytest is found in CI
- Skip DB-integration tests when `RUN_INTEGRATION_TESTS` not set

---

## [0.1.1] — 2026-02-24

### Fixed
- CI python-lint + frontend build
- Pin ruff==0.9.10, fix all violations, restore strict config
- Remove temp diagnostic scripts from CI commit

---

## [0.1.0] — 2026-02-22

### Added
- Initial Nexus Core V1 platform
- All agents productionized (server, email, DNS, carrier, storage, secrets, notifications, PBX)
- Agent registry with heartbeat monitoring
- Knowledge Base with RAG pipeline (pgvector embeddings)
- Nexus Portal (React + Ant Design)
- Event bus (Postgres-backed)
- System status automations (sync, checks, daily digest)
- Full end-to-end test suite (93 tests)
