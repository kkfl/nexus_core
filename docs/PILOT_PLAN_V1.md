# Nexus Core V1: Pilot Rollout Plan

This document outlines the strategy for piloting Nexus Core V1, the initial users, in-scope scenarios, and risk mitigations.

## Pilot Goals
1. Validate the stability of the core Orchestration & Persona RAG pipelines under light but continuous usage.
2. Prove the effectiveness of the Canonical System of Record (SoR) for centralizing infrastructure telemetry (PBX, Monitoring, Carrier).
3. Validate that "ReadOnly" Role-Based Access Control and Persona Policy enforcement correctly block unsanctioned agent writes in a real-world setting.
4. Establish baselines for agent reliability and task failure rates.

## Pilot Phases
- **Phase 0: Internal Dry Run (Automated)**
  - Execution of the automated Golden Paths suite against a mock-agent ecosystem.
  - Validation of all telemetry, UI rendering, and audit logs.
- **Phase 1: Operator-Only Usage**
  - IT Operators and Tier 2 Support engineers use the V1 Portal as a "Read-Only Observability Pane" for active PBX and Carrier infrastructure.
  - Manual triggers of inventory snapshots and KB document ingestion.
- **Phase 2: Limited Agent Automation**
  - Integration of the Monitoring Agent to automatically generate `triage.alert` tasks into the queue when Nagios/Datadog alerts trigger.
  - Read-Only agents deployed against production replicas.

## Roles & Responsibilities
- **admin (Owner)**: Responsible for overall system health, managing agent credentials, creating Personas, and defining task routing rules.
- **operator (Daily User)**: Daily triage engineers who log into the portal to review the System of Record, check Agent health, and ingest Knowledge Base documents as standard operating procedure.
- **reader (Stakeholder Visibility)**: Read-only accounts provided to project managers and adjacent engineering teams to observe Nexus automation progress and task histories without mutation rights.

## In-Scope Workflows
- **PBX Inventory Snapshots**: Scheduled or on-demand retrieval of extensions and trunks from target PBXs into the Canonical SoR.
- **Monitoring Ingestion + Triage Tasks**: Receiving generic monitoring JSON payloads and having a scoped persona generate human-readable triage tasks.
- **KB Ingest + RAG Search**: Operators uploading Markdown documentation to the global namespace and verifying RAG extraction via manual or agent-driven queries.
- **Carrier Snapshot Inventory**: Periodic retrieval of DID and trunk availability from downstream carrier SIP providers.
- **Storage Read Operations**: Validating MinIO object presence, stats, and generating presigned URLs.

## Out-of-Scope Workflows
- **Autonomous Auto-Remediation**: Agents will *diagnose* and *triage*, but will not be authorized to execute mutative fix scripts (e.g., restarting services) in V1.
- **Production PBX Write Actions**: Agents cannot create, delete, or modify user extensions on live voice systems.
- **Carrier Ordering / 10DLC Actions**: Agents will not interface with billing or compliance carrier endpoints.

## Risk Register & Mitigations
- **Risk:** Agents attempt unsafe mutative actions due to prompt drift.
  - *Mitigation:* `deny_task_types` defined heavily on all Phase 1/2 Personas. RAG bounds strictly enforced via API routing.
- **Risk:** System of Record gets out of sync with downstream infrastructure.
  - *Mitigation:* The SoR is designed as an eventually-consistent cache. Operators are trained to view the `updated_at` column in the Portal to verify staleness.
- **Risk:** Secret API keys are leaked into Agent logs.
  - *Mitigation:* Structlog redaction filters sanitize strings matching "key", "secret", "password", etc., at the stdout boundary before ingestion into external aggregators.
