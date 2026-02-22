# Nexus Core Backup & Feature Backlog (V1.1 -> V2.0)

This backlog is prioritized for execution immediately following the successful completion of Phase 2 of the V1 Pilot.

## UX Improvements (Portal)
- **Live Tail Logs** [M]
  - *Description:* Stream stdout/stderr from `nexus-worker` directly into the Portal Task View modal.
  - *Why:* Dramatically reduces the need for operators to SSH into Jump Hosts during triage.
- **Global Search Pane** [S]
  - *Description:* Omni-search bar to correlate Entities, Tasks, and Audits by a single `external_ref` or IP address.

## Agent Expansion
- **PBX Write Capabilities** [L]
  - *Description:* Build endpoints and agent tools for `pbx.extension.create` and `pbx.route.update`.
  - *Why:* Unlocks auto-provisioning workflows.
  - *Dependency:* Requires strict Role-Based approvals inserted into the async queue before dispatch.
- **Real DNS Provider Integrations** [M]
  - *Description:* Replace `dns-agent` mocks with Cloudflare/Route53 live provider SDKs.

## Observability
- **Grafana / Prometheus Stack** [L]
  - *Description:* Stand up a local Prometheus scraper and Grafana dashboard utilizing the `/metrics` endpoint.
  - *Why:* Replaces the need for manual polling of the DB `metrics_events` table for executive dashboards.

## RAG Enhancements
- **Dynamic Chunking & Citations** [M]
  - *Description:* Return source document page numbers and chunk text explicitly alongside the generated Agent context so Portal UI can highlight "Where the agent learned this".
  - *Why:* Builds operator trust in AI actions.
- **Tenant-Scoped Namespaces** [S]
  - *Description:* Enforce namespace limits strictly by Organization ID instead of just global overrides.

## Security & Reliability
- **SSO Integration (SAML/OIDC)** [L]
  - *Description:* Deprecate local DB passwords in favor of Entra ID / Okta for portal logins.
- **mTLS Agent Communications** [L]
  - *Description:* Issue client certificates to Agents to cryptographically guarantee identity, augmenting the Bearer token logic.
- **Worker Auto-Scaling** [M]
  - *Description:* Emit queue depth metrics so Kubernetes/Nomad can horizontally scale the `nexus-worker` container automatically.
