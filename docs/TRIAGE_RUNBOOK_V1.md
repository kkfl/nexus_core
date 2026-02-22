# Nexus Core V1: Triage & Support Runbook

This guide covers operational procedures for Tier 2 personnel managing the Nexus Core V1 Pilot.

## Handling Alert Tasks (`triage.alert`)

When the Monitoring Agent creates an alert task:
1. **Locate in Portal**: Navigate to Orchestration -> Tasks. Filter by type `triage.alert`.
2. **Review Artifacts**: Click "View Details" on the task row. Open the generated Artifacts to read the Agent's plain-English diagnosis of the Nagios/JSON alert.
3. **Verify Agent Health**: If the artifact is missing or incomplete, check Orchestration -> Agents. Note the "Status" pill (Healthy vs Offline) and "Last Ping".
4. **Resubmit Safely**: If an agent failed due to a transient network error, you can rerun the task safely. Extract the JSON Payload from the task details, and submit a new Task over the API using a randomized `X-Correlation-Id` header to track the retry chain.

## Common Core Failure Patterns

- **Agent Unreachable (HTTP 502/504)**
  - *Symptom:* Task remains in `running` then hits `failed` with a connection timeout artifact.
  - *Fix:* Verify the Agent's host container is up. Ensure the `base_url` defined in the Agent Registry is resolvable from the `nexus-worker` Docker network.

- **Persona Policy Violation (HTTP 403 / Failed Task)**
  - *Symptom:* Task fails immediately with `persona_task_type_denied`.
  - *Fix:* The task type requested is strictly forbidden by the `deny_task_types` array for the routing Persona. Or, the task requires a capability the Agent lacks. Check `Persona Defaults` and ensure the mapping is correct.

- **RAG Disabled / Namespace Denied**
  - *Symptom:* Agent logs indicate missing context.
  - *Fix:* Ensure the Task Route `needs_rag` is True, and the `rag_namespaces` includes the namespace where your documents were ingested (usually `global`).

- **Storage Writes Disabled**
  - *Symptom:* Agent throws an error attempting to write to MinIO.
  - *Fix:* `ENABLE_STORAGE_WRITES` must be set to `true` in the global `.env` file for the API.

## Break-Glass Procedures (Admin Only)

- **Disable an Agent**: Send a PATCH to `/agents/{id}` setting `is_active: false`. The worker will gracefully skip dispatching new tasks to this node.
- **Disable a Route**: Delete the Task Route mapping from the DB to instantly stop acceptance of that task type.
- **Change Defaults**: Use the Portal "Defaults & Overrides" page to quickly point a globally failing task type to a "Null" or "Mock" persona version.
- **Rotate Agent Keys**: Run `curl -X POST /auth/api-keys/{id}/rotate -H "Authorization: Bearer <TOKEN>"`. Update the downstream agent immediately with the returned plaintext key.
