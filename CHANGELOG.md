# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
