# Agent Registry

The `agent_registry` is the single source of truth for agent discovery, capabilities, and routing across the Nexus platform. It prevents hardcoded URLs and ports by allowing services (like `nexus_api`) to dynamically resolve agent endpoints at runtime.

## Core Concepts

*   **Agents:** High-level definitions of a logical service (e.g., `dns-agent`).
*   **Deployments:** Specific physical instantiations of an agent. Deployments can be global (for all tenants) or specific to a `tenant_id` and `env`. They contain the `base_url`, `auth_scheme`, and `auth_secret_alias`.
*   **Capabilities:** A push-model registry where agents or the platform write schemas describing what an agent can do (inputs/outputs).

## Multi-Tenancy Resolution
When a platform component (like `nexus_api`) wants to talk to `dns-agent` for `tenant_xyz`, it uses the `AgentRegistryClient`. 
1. The client looks up `dns-agent` deployments for the given `env`.
2. It attempts to find an exact match for `tenant_id=tenant_xyz`.
3. If no exact match is found, it falls back to a global deployment (`tenant_id=null`).
4. It returns a `ResolvableAgent` object containing the `base_url` and authentication hints.

## Authentication
The Agent Registry protects its own API using the platform-standard `X-Service-ID` and `X-Agent-Key` pattern. 
The keys allowed to mutate the registry are defined in the `AGENT_REGISTRY_KEYS` environment variable.

## Development

To run locally (outside of docker):

```bash
uvicorn apps.agent_registry.main:app --reload --port 8012
```
