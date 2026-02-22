# Nexus Core V1: Success Metrics & Instrumentation

This document defines the quantitative success metrics for the Nexus V1 pilot and how telemetry is collected.

## 1. Success Metrics

### Adoption Metrics
- **Active Logins per Week**: Target > 10 unique operator logins per week during Phase 1.
- **Tasks Created per Week**: Target > 500 tasks (combination of manual and monitoring triggers).
- **Successful Task Completion Rate**: Target > 95% across all reads.

### Reliability Metrics
- **Task Failure Rate by Type**: Alerting threshold set at > 5% failure rate for `pbx.snapshot` and `monitoring.ingest`.
- **Agent Unreachable Rate**: Alert if `agent_checkin` events drop by > 10% WoW (Week over Week).
- **Median Task Latency**: < 5 seconds for cache/lookup tasks; < 60 seconds for inventory aggregation tasks.

### Value Metrics
- **Time-to-Triage for Alerts**: Compare the timestamps of `monitoring.ingest` vs human acknowledgment in the SoR. Target < 15 minutes.
- **Reduction in Manual Steps**: Measure the reduction of manual portal logins to FreePBX/Carrier portals now that data is aggregated in the Canonical SoR.

### Security Metrics
- **Policy Denials Count**: Expected to be non-zero during early RAG tuning, but should plateau. Sudden spikes indicate agent hallucination or malicious injection attempts.
- **Secrets Decrypt Count**: Watched closely for anomalies against the baseline agent execution rate.

## 2. Telemetry & Instrumentation (V1)

To support this without massive external dependencies like Datadog/NewRelic in V1, Nexus uses a lightweight `metrics_events` table in Postgres.

The `nexus-api` and `nexus-worker` emit explicit telemetry for strategic events:
- `login`
- `task_create`
- `task_succeeded` / `task_failed` / `task_dead_letter`
- `agent_checkin`
- `persona_policy_violation`

*Note: In future iterations, this table will be deprecated in favor of native OpenTelemetry spans.*
