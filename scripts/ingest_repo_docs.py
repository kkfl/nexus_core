"""Repo Docs KB Ingest — Seed the knowledge base with Nexus documentation.

Usage:
    python scripts/ingest_repo_docs.py [--api-url http://localhost:8000]

This script:
1. Walks predefined safe documentation paths in the repo.
2. Creates a "repo-docs" KB source if one doesn't exist.
3. For each file, uploads via the text ingest API endpoint.
4. Queues embedding for each document.
"""

import argparse
import os
import time

import httpx

# Safe doc paths relative to repo root (no secrets, .env, credentials)
SAFE_DOC_PATHS = [
    "README.md",
    "CHANGELOG.md",
    "docs/BACKLOG_V1_1.md",
    "docs/PILOT_PLAN_V1.md",
    "docs/SUCCESS_METRICS_V1.md",
    "docs/TRIAGE_RUNBOOK_V1.md",
    "docs/agent_ops_runbook.md",
    "apps/agent_registry/README.md",
    "apps/agent_registry/RUNBOOK.md",
    "apps/automation_agent/README.md",
    "apps/automation_agent/RUNBOOK.md",
    "apps/dns_agent/README.md",
    "apps/dns_agent/RUNBOOK.md",
    "apps/nexus_portal/README.md",
    "apps/notifications_agent/README.md",
    "apps/notifications_agent/RUNBOOK.md",
    "apps/pbx_agent/README.md",
    "apps/pbx_agent/RUNBOOK.md",
    "apps/secrets_agent/README.md",
    "infra/prod/docs/BACKUPS.md",
    "infra/prod/docs/GO_LIVE.md",
    "infra/prod/docs/OPERATIONS.md",
    "infra/prod/docs/PRODUCTION.md",
    "tools/golden_paths/README.md",
]

# Paths that must NEVER be ingested
DENY_LIST_PATTERNS = [
    ".env",
    "secret",
    "credential",
    "private_key",
    "id_rsa",
]


def is_safe(path: str) -> bool:
    lower = path.lower()
    return not any(p in lower for p in DENY_LIST_PATTERNS)


def get_token(client, api_url):
    r = client.post(
        f"{api_url}/auth/login",
        data={"username": "admin@nexus.local", "password": "admin_password"},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def ensure_source(client, headers, api_url):
    """Get or create the 'repo-docs' KB source."""
    r = client.get(f"{api_url}/kb/sources", headers=headers)
    sources = r.json()
    for s in sources:
        if s.get("name") == "repo-docs":
            return s["id"]

    r = client.post(
        f"{api_url}/kb/sources", json={"name": "repo-docs", "kind": "manual"}, headers=headers
    )
    return r.json()["id"]


def main():
    parser = argparse.ArgumentParser(description="Ingest repo documentation into KB")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--namespace", default="repo-docs")
    parser.add_argument("--dry-run", action="store_true", help="List files without ingesting")
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Resolve and validate paths
    files = []
    for rel_path in SAFE_DOC_PATHS:
        abs_path = os.path.join(repo_root, rel_path)
        if not os.path.exists(abs_path):
            print(f"  SKIP (not found): {rel_path}")
            continue
        if not is_safe(rel_path):
            print(f"  SKIP (deny list):  {rel_path}")
            continue
        size = os.path.getsize(abs_path)
        files.append((rel_path, abs_path, size))
        print(f"  OK ({size:>6} bytes): {rel_path}")

    print(f"\n  Total: {len(files)} files, {sum(f[2] for f in files):,} bytes")

    if args.dry_run:
        print("\n  --dry-run: no ingestion performed.")
        return

    # Auth + source
    client = httpx.Client(timeout=30)
    token = get_token(client, args.api_url)
    headers = {"Authorization": f"Bearer {token}"}
    source_id = ensure_source(client, headers, args.api_url)
    print(f"\n  Source: repo-docs (id={source_id})")

    # Ingest each file
    ingested = []
    for rel_path, abs_path, _size in files:
        with open(abs_path, encoding="utf-8", errors="ignore") as f:
            text = f.read()

        title = rel_path.replace("\\", "/")
        r = client.post(
            f"{args.api_url}/kb/documents/text",
            json={
                "source_id": source_id,
                "namespace": args.namespace,
                "title": title,
                "text": text,
            },
            headers=headers,
        )

        if r.status_code == 200:
            doc_id = r.json().get("document_id")
            ingested.append((title, doc_id))
            print(f"  INGESTED: {title} -> doc_id={doc_id}")
        else:
            print(f"  ERROR:    {title} -> {r.status_code}: {r.text[:100]}")

        # Small delay to avoid overwhelming the worker queue
        time.sleep(0.2)

    print(f"\n  Ingested {len(ingested)} documents. Worker will embed them in the background.")
    print(f"  Monitor with: curl http://localhost:8000/kb/documents?namespace={args.namespace}")
    print("\n  Wait ~60s for embedding to complete, then run:")
    print(f"    python scripts/eval_runner.py --api-url {args.api_url}")


if __name__ == "__main__":
    main()
