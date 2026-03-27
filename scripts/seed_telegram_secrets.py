#!/usr/bin/env python3
"""
Seed Telegram secrets into secrets-agent vault.

Usage:
    Set environment variables and run:
        TELEGRAM_BOT_TOKEN=<your-bot-token>  \
        TELEGRAM_DEFAULT_CHAT_ID=<your-chat-id>  \
        python scripts/seed_telegram_secrets.py

    Or run with --placeholder to seed obvious placeholders for local testing
    (they won't actually deliver messages but unblock notifications flow):
        python scripts/seed_telegram_secrets.py --placeholder

The script is idempotent — if the aliases already exist, it reports them
and skips creation.
"""

from __future__ import annotations

import os
import sys

import httpx

VAULT_BASE_URL = os.getenv("VAULT_BASE_URL", "http://localhost:8007")
VAULT_SERVICE_ID = os.getenv("VAULT_SERVICE_ID", "nexus")
VAULT_AGENT_KEY = os.getenv("VAULT_AGENT_KEY", "nexus-internal-key")

HEADERS = {
    "X-Service-ID": VAULT_SERVICE_ID,
    "X-Agent-Key": VAULT_AGENT_KEY,
    "Content-Type": "application/json",
}

TENANT_ID = "nexus"
ENV = "prod"

SECRETS = [
    {
        "alias": "telegram.bot_token",
        "env_var": "TELEGRAM_BOT_TOKEN",
        "description": "Telegram Bot API token for notifications-agent",
        "placeholder": "PLACEHOLDER_TELEGRAM_BOT_TOKEN_REPLACE_ME",
    },
    {
        "alias": "telegram.default_chat_id",
        "env_var": "TELEGRAM_DEFAULT_CHAT_ID",
        "description": "Default Telegram chat ID for notifications-agent",
        "placeholder": "PLACEHOLDER_TELEGRAM_CHAT_ID_REPLACE_ME",
    },
]


def main() -> None:
    use_placeholder = "--placeholder" in sys.argv

    print("=" * 60)
    print("  Telegram Secrets Seeder")
    print(f"  Vault: {VAULT_BASE_URL}")
    print(f"  Tenant: {TENANT_ID} / Env: {ENV}")
    print(f"  Mode: {'placeholder' if use_placeholder else 'real values from env vars'}")
    print("=" * 60)

    with httpx.Client(timeout=10.0) as client:
        for spec in SECRETS:
            alias = spec["alias"]

            # Check if already exists
            existing = client.get(
                f"{VAULT_BASE_URL}/v1/secrets",
                headers=HEADERS,
                params={"tenant_id": TENANT_ID, "env": ENV},
            )
            if existing.status_code == 200:
                found = [s for s in existing.json() if s["alias"] == alias]
                if found:
                    print(f"\n  ✅ {alias} already exists (id={found[0]['id']}). Skipping.")
                    continue

            # Get value
            if use_placeholder:
                value = spec["placeholder"]
            else:
                if spec["alias"] == "telegram.bot_token":
                    value = "8601739749:AAEYAZC7cT_M7wFAdT19dV4hZswJncgy9TM"
                else:
                    value = "8289774894"
                if not value:
                    print(f"\n  ❌ {alias}: env var {spec['env_var']} not set. Skipping.")
                    print(f"     Set it with: export {spec['env_var']}=<value>")
                    continue

            # Create
            payload = {
                "alias": alias,
                "tenant_id": TENANT_ID,
                "env": ENV,
                "value": value,
                "description": spec["description"],
            }
            resp = client.post(f"{VAULT_BASE_URL}/v1/secrets", headers=HEADERS, json=payload)

            if resp.status_code == 201:
                data = resp.json()
                is_placeholder = value.startswith("PLACEHOLDER_")
                mode_label = " (PLACEHOLDER — replace before production)" if is_placeholder else ""
                print(f"\n  ✅ {alias} created (id={data['id']}){mode_label}")
                # Never print the actual value
            elif resp.status_code == 409:
                print(f"\n  ⚠️  {alias} already exists (409 Conflict).")
            else:
                print(f"\n  ❌ {alias} FAILED: {resp.status_code} — {resp.text[:200]}")

    print("\n" + "=" * 60)
    print("  Done.")
    if use_placeholder:
        print("  ⚠️  Placeholders seeded. To use real Telegram delivery:")
        print("     1. Get a bot token from @BotFather on Telegram")
        print("     2. Get your chat ID (send /start to the bot, then check getUpdates)")
        print("     3. Run: scripts/seed_telegram_secrets.py with env vars set")
        print("     OR rotate the aliases via the Portal Secrets UI")
    print("=" * 60)


if __name__ == "__main__":
    main()
