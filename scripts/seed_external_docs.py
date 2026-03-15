"""Seed External Documentation — Populate Nexus KB with service documentation.

Usage:
    python scripts/seed_external_docs.py [--api-url http://localhost:8000] [--dry-run]

This script ingests curated documentation for external services that Nexus
integrates with (Vultr, Cloudflare, iRedMail) plus Nexus-specific operational
guides. The documents are ingested via the KB text ingest API and embedded by
the worker in the background.

Unlike scraping raw HTML (which produces noisy chunks), this script uses
pre-curated markdown documentation focused on the use cases people actually
ask about: provisioning VMs, managing DNS, creating mailboxes, etc.
"""

import argparse
import time

import httpx

# ── Curated documentation entries ──────────────────────────────────────
# Each entry: (title, namespace, markdown content)

EXTERNAL_DOCS: list[tuple[str, str, str]] = []


def _add(title: str, content: str, namespace: str = "external-docs"):
    EXTERNAL_DOCS.append((title, namespace, content))


# ─────────────────────────────────────────────────────────────────────
# VULTR API DOCUMENTATION
# ─────────────────────────────────────────────────────────────────────

_add(
    "Vultr API — Introduction & Authentication",
    """\
# Vultr API v2 — Introduction & Authentication

The Vultr API v2 is a RESTful API at `https://api.vultr.com/v2/`.
All requests use JSON and require an API key passed via the
`Authorization: Bearer {API_KEY}` header.

## Authentication
```
Authorization: Bearer YOUR_VULTR_API_KEY
```

## Pagination
Vultr uses cursor-based pagination:
- `per_page` — items per page (default 100, max 500)
- `cursor` — opaque cursor from previous response's `meta.links.next`

## Rate Limiting
Rate limits are per-API-key. Responses include `X-RateLimit-Limit`,
`X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers.

## Common Response Codes
| Code | Meaning |
|------|---------|
| 200  | Success |
| 201  | Created |
| 204  | No Content (successful delete) |
| 400  | Bad Request — invalid parameters |
| 401  | Unauthorized — invalid or missing API key |
| 403  | Forbidden — insufficient permissions |
| 404  | Not Found |
| 429  | Too Many Requests |
| 500  | Internal Server Error |
""",
)

_add(
    "Vultr API — Instances (Create, List, Manage VMs)",
    """\
# Vultr API — Instances

## List All Instances
```
GET https://api.vultr.com/v2/instances
```
Returns a list of all VPS instances on your account.
Supports query params: `per_page`, `cursor`, `tag`, `label`, `main_ip`, `region`.

## Create Instance (Provision a New VM)
```
POST https://api.vultr.com/v2/instances
Content-Type: application/json

{
  "region": "ewr",
  "plan": "vc2-1c-1gb",
  "os_id": 387,
  "label": "my-server",
  "hostname": "my-server",
  "sshkey_id": ["ssh-key-id-here"],
  "backups": "enabled",
  "tags": ["web", "production"],
  "enable_ipv6": true,
  "user_data": "base64-encoded-cloud-init"
}
```
**Required**: `region`, `plan`, and one of `os_id`, `app_id`, `image_id`, or `snapshot_id`.

## Get Instance Details
```
GET https://api.vultr.com/v2/instances/{instance-id}
```
Returns full details: IP addresses, power status, plan, region, OS, etc.

## Update Instance
```
PATCH https://api.vultr.com/v2/instances/{instance-id}
```
Updatable fields: `plan` (upgrade), `label`, `tag`, `backups`, `firewall_group_id`.

## Delete Instance
```
DELETE https://api.vultr.com/v2/instances/{instance-id}
```

## Power Actions
| Action | Method |
|--------|--------|
| Start | `POST /v2/instances/{id}/start` |
| Reboot | `POST /v2/instances/{id}/reboot` |
| Halt (shutdown) | `POST /v2/instances/{id}/halt` |
| Reinstall OS | `POST /v2/instances/{id}/reinstall` |

## How Nexus Provisions VMs via Vultr
Nexus uses the `server_agent` to interact with Vultr's API. To provision a VM:
1. The user creates a task of type `server.provision` via the Nexus API
2. The `server_agent` receives the task and calls Vultr's Create Instance endpoint
3. It polls until the instance status is `active`
4. It syncs the server details back into Nexus's server inventory
""",
)

_add(
    "Vultr API — Plans, Regions, and OS",
    """\
# Vultr API — Plans, Regions, and Operating Systems

## List Plans
```
GET https://api.vultr.com/v2/plans
```
Returns available plans with CPU, RAM, disk, bandwidth, and pricing.
Filter by `type`: `vc2` (cloud), `vhf` (high frequency), `vdc` (dedicated).

Common plans:
| Plan ID | CPU | RAM | Disk | Monthly |
|---------|-----|-----|------|---------|
| vc2-1c-1gb | 1 vCPU | 1 GB | 25 GB SSD | $5 |
| vc2-1c-2gb | 1 vCPU | 2 GB | 55 GB SSD | $10 |
| vc2-2c-4gb | 2 vCPU | 4 GB | 80 GB SSD | $20 |
| vc2-4c-8gb | 4 vCPU | 8 GB | 160 GB SSD | $40 |

## List Regions
```
GET https://api.vultr.com/v2/regions
```
Returns data centers with location and features.
Common regions: `ewr` (New Jersey), `ord` (Chicago), `lax` (LA), `ams` (Amsterdam).

## List Operating Systems
```
GET https://api.vultr.com/v2/os
```
Returns available OS images with `id`, `name`, `arch`, `family`.

## List SSH Keys
```
GET https://api.vultr.com/v2/ssh-keys
POST https://api.vultr.com/v2/ssh-keys  (create new)
```

## Snapshots
```
GET https://api.vultr.com/v2/snapshots
POST https://api.vultr.com/v2/snapshots  {"instance_id": "...", "description": "..."}
```
""",
)

_add(
    "Vultr API — DNS Management",
    """\
# Vultr API — DNS Management

## List DNS Domains
```
GET https://api.vultr.com/v2/domains
```

## Create DNS Domain
```
POST https://api.vultr.com/v2/domains
{"domain": "example.com"}
```

## List DNS Records
```
GET https://api.vultr.com/v2/domains/{domain}/records
```

## Create DNS Record
```
POST https://api.vultr.com/v2/domains/{domain}/records
{
  "type": "A",
  "name": "www",
  "data": "1.2.3.4",
  "ttl": 300,
  "priority": 0
}
```
Supported record types: A, AAAA, CNAME, MX, TXT, NS, SRV, CAA.

## Update DNS Record
```
PATCH https://api.vultr.com/v2/domains/{domain}/records/{record-id}
```

## Delete DNS Record
```
DELETE https://api.vultr.com/v2/domains/{domain}/records/{record-id}
```
""",
)

# ─────────────────────────────────────────────────────────────────────
# CLOUDFLARE API DOCUMENTATION
# ─────────────────────────────────────────────────────────────────────

_add(
    "Cloudflare API — Authentication & Basics",
    """\
# Cloudflare API — Authentication & Basics

Base URL: `https://api.cloudflare.com/client/v4/`

## Authentication Methods

### API Token (Recommended)
```
Authorization: Bearer {API_TOKEN}
```
Create tokens at dashboard.cloudflare.com > My Profile > API Tokens.
Tokens can be scoped to specific zones and permissions.

### Global API Key (Legacy)
```
X-Auth-Email: {EMAIL}
X-Auth-Key: {GLOBAL_API_KEY}
```

## Response Format
All responses are JSON with this structure:
```json
{
  "success": true,
  "errors": [],
  "messages": [],
  "result": { ... },
  "result_info": { "page": 1, "per_page": 20, "count": 1, "total_count": 1 }
}
```

## Pagination
Use `page` and `per_page` query parameters. Default `per_page` is 20, max is 100.

## Rate Limiting
1200 requests per 5 minutes per user.
""",
)

_add(
    "Cloudflare API — DNS Zones and Records",
    """\
# Cloudflare API — DNS Zones and Records

## List Zones
```
GET /client/v4/zones
GET /client/v4/zones?name=example.com  (filter by domain)
```

## Get Zone Details
```
GET /client/v4/zones/{zone_id}
```

## List DNS Records
```
GET /client/v4/zones/{zone_id}/dns_records
GET /client/v4/zones/{zone_id}/dns_records?type=A&name=www.example.com
```
Supports filters: `type`, `name`, `content`, `proxied`, `order`, `direction`.

## Create DNS Record
```
POST /client/v4/zones/{zone_id}/dns_records
{
  "type": "A",
  "name": "www.example.com",
  "content": "1.2.3.4",
  "ttl": 3600,
  "proxied": true
}
```
When `proxied: true`, traffic goes through Cloudflare's CDN and DDoS protection.

## Update DNS Record
```
PUT /client/v4/zones/{zone_id}/dns_records/{record_id}
```
Same body as create. PUT replaces the entire record.

## Patch DNS Record
```
PATCH /client/v4/zones/{zone_id}/dns_records/{record_id}
```
Partial update — only send fields you want to change.

## Delete DNS Record
```
DELETE /client/v4/zones/{zone_id}/dns_records/{record_id}
```

## Common DNS Record Types
| Type | Purpose | Example Content |
|------|---------|-----------------|
| A | IPv4 address | `1.2.3.4` |
| AAAA | IPv6 address | `2001:db8::1` |
| CNAME | Alias | `www.example.com` |
| MX | Mail server | `mail.example.com` (priority field required) |
| TXT | Text record | `v=spf1 include:...` |
| SRV | Service record | `target:port` |

## How Nexus Uses Cloudflare
Nexus uses the `dns_agent` to manage Cloudflare DNS records. When provisioning
a new server, Nexus can automatically:
1. Create A/AAAA records pointing to the new server's IP
2. Set up reverse DNS
3. Manage SSL/TLS settings
4. Toggle proxy status (orange cloud on/off)
""",
)

_add(
    "Cloudflare API — SSL, Firewall, and Page Rules",
    """\
# Cloudflare API — SSL, Firewall, and Page Rules

## SSL/TLS Mode
```
GET /client/v4/zones/{zone_id}/settings/ssl
PATCH /client/v4/zones/{zone_id}/settings/ssl
{"value": "full"}
```
Modes: `off`, `flexible`, `full`, `strict` (full strict).

## Firewall Rules
```
GET /client/v4/zones/{zone_id}/firewall/rules
POST /client/v4/zones/{zone_id}/firewall/rules
```

## WAF Rules
```
GET /client/v4/zones/{zone_id}/firewall/waf/packages
```

## Page Rules
```
GET /client/v4/zones/{zone_id}/pagerules
POST /client/v4/zones/{zone_id}/pagerules
{
  "targets": [{"target": "url", "constraint": {"operator": "matches", "value": "*.example.com/*"}}],
  "actions": [{"id": "always_use_https"}],
  "priority": 1,
  "status": "active"
}
```

## Cache Purge
```
POST /client/v4/zones/{zone_id}/purge_cache
{"purge_everything": true}
```
Or purge specific URLs:
```json
{"files": ["https://example.com/style.css"]}
```
""",
)

# ─────────────────────────────────────────────────────────────────────
# IREDMAIL DOCUMENTATION
# ─────────────────────────────────────────────────────────────────────

_add(
    "iRedMail — Admin API Overview",
    """\
# iRedMail — Admin API (iRedAdmin-Pro RESTful API)

## Overview
iRedAdmin-Pro provides a RESTful API for managing mail domains, users,
aliases, and policies. The API is disabled by default and must be enabled
in `settings.py`:

```python
ENABLE_RESTFUL_API = True
```

## Authentication
```
POST /api/login
{"username": "postmaster@example.com", "password": "..."}
```
Returns a cookie for subsequent requests. Alternatively, use the
`X-iRedMail-API-Key` header with a key generated from the admin panel.

## API Response Format
```json
{
  "_success": true,
  "_msg": "success message"
}
```
On error:
```json
{
  "_success": false,
  "_msg": "error description"
}
```
GET requests include `_data` with the result payload.
""",
)

_add(
    "iRedMail — Domain Management",
    """\
# iRedMail — Domain Management API

## Create Domain
```
POST /api/domain/{domain}
{"defaultQuota": "1024"}
```
Creates a new mail domain. `defaultQuota` is in MB.

## Get Domain Profile
```
GET /api/domain/{domain}
```

## Update Domain
```
PUT /api/domain/{domain}
{"maxQuota": "10240", "numberOfUsers": "100"}
```

## Delete Domain
```
DELETE /api/domain/{domain}
```
⚠️ This deletes ALL mailboxes under the domain.

## List All Domains
```
GET /api/domains
```
Returns all domains with user counts and quota info.
""",
)

_add(
    "iRedMail — Mailbox & User Management",
    """\
# iRedMail — Mailbox & User Management API

## Create Mail User
```
POST /api/user/{email}
{
  "password": "secure_password",
  "cn": "John Doe",
  "quota": "2048",
  "mailboxFormat": "maildir"
}
```
- `email` — full email address (e.g., `john@example.com`)
- `password` — plaintext, will be hashed by server
- `quota` — mailbox quota in MB
- `cn` — common name / display name

## Get User Profile
```
GET /api/user/{email}
```

## Update User
```
PUT /api/user/{email}
{"quota": "4096", "cn": "John D. Doe"}
```

## Delete User
```
DELETE /api/user/{email}
DELETE /api/user/{email}?keep_mailbox_days=7
```
Optional: keep mailbox on disk for N days before purging.

## Rename User
```
POST /api/rename/user/{old_email}/{new_email}
```

## List Users in Domain
```
GET /api/users/{domain}
GET /api/users/{domain}?page=1
```

## Bulk Operations
```
PUT /api/users/{domain}     (update multiple)
DELETE /api/users/{domain}  (delete all users in domain)
```

## How Nexus Uses iRedMail
Nexus uses the `email_agent` to manage mail accounts. Through the portal:
1. Admins can create new mailboxes for team members
2. Set quota limits and manage aliases
3. Configure spam policies and whitelists
4. The email agent connects via SSH tunnel through a jump host to
   reach the iRedMail server on the internal network
""",
)

_add(
    "iRedMail — Aliases, Spam, and Policies",
    """\
# iRedMail — Aliases, Spam Policies, and Throttling

## Mail Aliases
```
POST /api/alias/{email}             (create)
GET  /api/alias/{email}             (get details)
PUT  /api/alias/{email}             (update)
DELETE /api/alias/{email}           (delete)
GET  /api/aliases/{domain}          (list all in domain)
```

## Mailing Lists
```
POST /api/maillist/{email}          (create subscribable list)
GET  /api/maillist/{email}          (get details)
PUT  /api/maillist/{email}          (update)
DELETE /api/maillist/{email}        (delete)
GET  /api/maillists/{domain}        (list all)
```

## Spam Policy
```
GET /api/spampolicy/global          (global policy)
GET /api/spampolicy/domain/{domain} (domain policy)
GET /api/spampolicy/user/{email}    (per-user policy)
POST /api/spampolicy/user/{email}   (set per-user policy)
DELETE /api/spampolicy/user/{email} (remove per-user policy)
```

## Throttling
```
GET  /api/throttle/global/inbound
GET  /api/throttle/global/outbound
POST /api/throttle/global/inbound   {"maxMsgs": 100, "msgSize": "10M"}
POST /api/throttle/{email}/inbound  (per-user throttle)
```

## Whitelisting/Blacklisting
```
GET  /api/wblist/global             (global list)
POST /api/wblist/global             {"whitelist": ["trusted@example.com"]}
POST /api/wblist/{email}            (per-user list)
GET  /api/wblist/{email}
```

## Greylisting
```
GET    /api/greylisting/global
POST   /api/greylisting/global      {"status": "active"}
GET    /api/greylisting/{domain}
POST   /api/greylisting/{domain}
DELETE /api/greylisting/{domain}     (disable for domain)
```
""",
)

# ─────────────────────────────────────────────────────────────────────
# NEXUS INTERNAL DOCUMENTATION
# ─────────────────────────────────────────────────────────────────────

_add(
    "Nexus — How to Interface with the Nexus API",
    """\
# How to Interface with the Nexus API

## Authentication
```
POST /auth/login
Content-Type: application/x-www-form-urlencoded

username=admin@nexus.local&password=your_password
```
Returns `{"access_token": "...", "token_type": "bearer"}`.
Use the token in subsequent requests:
```
Authorization: Bearer {access_token}
```

## Creating a Task (e.g., Provision a VM)
```
POST /tasks
{
  "type": "server.provision",
  "payload": {
    "provider": "vultr",
    "region": "ewr",
    "plan": "vc2-1c-2gb",
    "os_id": 387,
    "label": "web-prod-1",
    "hostname": "web-prod-1"
  }
}
```
This creates a task that will be picked up by the `server_agent`,
which will call Vultr's API to provision the instance.

## Checking Task Status
```
GET /tasks/{task_id}
```
Status lifecycle: `queued` → `running` → `succeeded` or `failed`.

## Using the Knowledge Base (Ask Nexus)
```
POST /kb/ask
{"query": "How do I create a new VM on Vultr?"}
```
Returns an AI-generated answer with citations from the KB.

## Key API Endpoints
| Endpoint | Description |
|----------|-------------|
| `POST /auth/login` | Authenticate and get JWT |
| `GET /dashboard/command-center` | Aggregated system overview |
| `POST /tasks` | Create a new task |
| `GET /tasks` | List tasks |
| `GET /servers` | List all servers |
| `POST /servers/sync` | Trigger server inventory sync |
| `GET /kb/sources` | List KB sources |
| `POST /kb/ask` | Ask Nexus a question |
| `POST /kb/search` | Raw vector search |
| `GET /agents` | List registered agents |
| `GET /events` | List system events |
""",
    namespace="repo-docs",
)

_add(
    "Nexus — Architecture Overview for Developers",
    """\
# Nexus Architecture Overview

Nexus is a multi-agent orchestration platform built with:
- **Backend**: FastAPI (Python) with async SQLAlchemy and PostgreSQL
- **Frontend**: React (TypeScript) with Vite
- **Worker**: Background job runner for async tasks and RAG embedding
- **Storage**: MinIO (S3-compatible) for artifacts and KB documents

## Agent Architecture
Nexus orchestrates multiple specialized agents:
| Agent | Purpose |
|-------|---------|
| `server_agent` | VM provisioning via Vultr/Proxmox |
| `dns_agent` | DNS management via Cloudflare |
| `email_agent` | Mail management via iRedMail |
| `carrier_agent` | SMS/Voice via Twilio |
| `storage_agent` | Backup/replication via MinIO/Synology |
| `pbx_agent` | PBX/telephony management |
| `automation_agent` | Custom automation workflows |
| `secrets_agent` | Credential management (Vault-like) |
| `notifications_agent` | Multi-channel notifications |

## Task Lifecycle
1. User or automation creates a task via `POST /tasks`
2. Worker's `_dispatch_task` finds eligible agent based on task type and capabilities
3. Agent receives the task payload + optional persona + RAG context
4. Agent executes and returns result with optional proposed writes
5. Worker applies entity writes (System of Record) and stores artifacts

## Event Bus
All actions emit events that are persisted and can trigger automations.
Events: `task.created`, `task.succeeded`, `agent.heartbeat`, `kb.document.indexed`, etc.

## RAG Pipeline (Ask Nexus)
1. Documents are ingested → chunked → embedded (fastembed BGE-small or OpenAI)
2. Embeddings stored in pgvector
3. On query: embed question → cosine similarity search → LLM synthesis → answer

## Key Environment Variables
| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection |
| `REDIS_URL` | Rate limiting, caching |
| `STORAGE_S3_*` | MinIO/S3 storage config |
| `OPENAI_API_KEY` | LLM for Ask Nexus answers |
| `LLM_PROVIDER` | `openai` or `disabled` |
""",
    namespace="repo-docs",
)


# ─────────────────────────────────────────────────────────────────────
# Script entrypoint
# ─────────────────────────────────────────────────────────────────────


def get_token(client: httpx.Client, api_url: str) -> str:
    r = client.post(
        f"{api_url}/auth/login",
        data={"username": "admin@nexus.local", "password": "admin_password"},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def ensure_source(client: httpx.Client, headers: dict, api_url: str, source_name: str) -> int:
    """Get or create a KB source."""
    r = client.get(f"{api_url}/kb/sources", headers=headers)
    sources = r.json()
    for s in sources:
        if s.get("name") == source_name:
            return s["id"]
    r = client.post(
        f"{api_url}/kb/sources",
        json={"name": source_name, "kind": "manual"},
        headers=headers,
    )
    return r.json()["id"]


def main():
    parser = argparse.ArgumentParser(
        description="Seed the Nexus KB with external service documentation"
    )
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview documents without ingesting"
    )
    args = parser.parse_args()

    print(f"\n  Nexus KB Seeder — {len(EXTERNAL_DOCS)} documents prepared\n")

    # Group by namespace for display
    by_ns: dict[str, list[tuple[str, str, str]]] = {}
    for title, ns, content in EXTERNAL_DOCS:
        by_ns.setdefault(ns, []).append((title, ns, content))

    for ns, docs in by_ns.items():
        print(f"  [{ns}]")
        for title, _, content in docs:
            print(f"    • {title} ({len(content):,} chars)")
        print()

    total_chars = sum(len(c) for _, _, c in EXTERNAL_DOCS)
    print(f"  Total: {len(EXTERNAL_DOCS)} docs, {total_chars:,} chars\n")

    if args.dry_run:
        print("  --dry-run: no ingestion performed.")
        return

    # Auth + sources
    client = httpx.Client(timeout=30)
    token = get_token(client, args.api_url)
    headers = {"Authorization": f"Bearer {token}"}

    # Cache source IDs by namespace
    source_ids: dict[str, int] = {}
    for ns in by_ns:
        source_name = ns  # Use namespace as source name
        source_ids[ns] = ensure_source(client, headers, args.api_url, source_name)
        print(f"  Source '{source_name}' => id={source_ids[ns]}")

    print()

    # Ingest
    ingested = 0
    for title, ns, content in EXTERNAL_DOCS:
        r = client.post(
            f"{args.api_url}/kb/documents/text",
            json={
                "source_id": source_ids[ns],
                "namespace": ns,
                "title": title,
                "text": content,
            },
            headers=headers,
        )

        if r.status_code == 200:
            doc_id = r.json().get("document_id")
            ingested += 1
            print(f"  ✓ {title} → doc_id={doc_id}")
        else:
            print(f"  ✗ {title} → {r.status_code}: {r.text[:100]}")

        time.sleep(0.3)  # Don't overwhelm the worker queue

    print(f"\n  Ingested {ingested}/{len(EXTERNAL_DOCS)} documents.")
    print("  Worker will embed them in the background (~60s).\n")
    print("  Test with:")
    print(f"    curl -X POST {args.api_url}/kb/ask -H 'Authorization: Bearer ...' \\")
    print("""      -d '{\"query\": \"How do I provision a VM on Vultr via Nexus?\"}'\n""")


if __name__ == "__main__":
    main()
