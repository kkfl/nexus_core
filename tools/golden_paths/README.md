# Nexus Core: Golden Paths

This directory contains scripted, repeatable end-to-end workflows that demonstrate the core value of Nexus V1. They act as automated smoke tests for the live API, utilizing mock agent infrastructure.

## Prerequisites

Ensure the full Nexus Docker ecosystem is running locally.

```bash
# From the root of the repository
docker compose up --build -d
```

## Running the Golden Paths

1. Setup your environment variables:
   ```bash
   cp env.example .env
   # Customize credentials if you changed the bootstrap defaults
   ```

2. Execute the orchestrator:
   ```bash
   ./run_all.sh
   ```

The script will iterate through `paths/*.sh`, executing:
1. KB ingestion and RAG searches
2. DNS Lookups enriched heavily by RAG context
3. PBX Inventory aggregation to the Canonical System of Record
4. Monitoring Ingests that dynamically spawn automated Triage Tasks
5. Storage API dispatching
6. Carrier Snapshot orchestration
7. Database idempotency proofs via Conflict handling
8. Audit observability

## Portal Verification

After running the golden paths, log into the Nexus Portal at `http://localhost:3000` (`admin@local.host` | `admin`).

You can verify the automated workflows by checking:
- **Tasks Page**: Search for Tasks or filter. Notice the tasks generated with `correlation_id` values starting with `golden-`. Click "View Details" to see artifacts.
- **Entities Page**: You will see populated canonical references for `pbx_endpoint`, `mon_service`, `carrier_did`, and `carrier_trunk`.
- **Knowledge Base**: Check Documents to see the text documents injected by the automation.
- **Audits Page**: View the trail of login events, task executions, SoR upserts, and explicitly triggered Persona Policy denials.
