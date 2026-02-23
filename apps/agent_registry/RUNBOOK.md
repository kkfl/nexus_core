# Operational Runbook: Agent Registry

## Overview
The Agent Registry is a critical path dependency. If it goes down, the orchestrator (`nexus_api`) cannot resolve agent URLs to dispatch tasks, effectively halting system operations.

## Dependencies
*   **PostgreSQL:** Stores the registry metadata.
*   **Platform Initialization:** By default, `nexus_api` currently seeds the agent registry during its FastAPI lifespan startup phase.

## Troubleshooting

### Issue: "Agent not found" or "Deployment not found"
If the orchestrator complains it cannot find an agent:
1. Verify the `agent_registry` service is healthy.
2. Check the `nexus_api` startup logs to ensure `agent_registry_seeded` appeared.
3. Use the admin key to query the registry manually:
   ```bash
   curl -H "X-Service-ID: admin" -H "X-Agent-Key: <admin-key>" http://agent-registry:8012/v1/agents
   ```
4. Check if the deployment matching the `tenant_id` and `env` exists via `/v1/deployments`.

### Issue: Registration conflicts (409)
The `nexus-api` seeding is designed to ignore `409 Conflict` errors when creating agents/deployments that already exist. If you see errors about duplicate unique constraints, confirm you are not explicitly passing clashing UUIDs or manually inserting data outside the application.

## Scaling
The service is stateless except for the database and can be scaled horizontally. Database load is read-heavy (agent resolution) and can be easily cached at the application level if required in future versions.
