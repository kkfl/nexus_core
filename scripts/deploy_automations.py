import json
import os
import sys

import requests

BASE_URL = os.getenv("AUTOMATION_AGENT_URL", "http://localhost:8013/v1/automations")
HEADERS = {
    "X-Service-ID": "nexus",
    "X-Agent-Key": os.getenv("NEXUS_AUTOMATION_KEY", "<REDACTED_API_KEY>"),
    "Content-Type": "application/json",
}


def main():
    automations_dir = os.path.join(os.path.dirname(__file__), "..", "automations")
    if not os.path.exists(automations_dir):
        print(f"Error: directory {automations_dir} not found.")
        sys.exit(1)

    success_count = 0
    for filename in os.listdir(automations_dir):
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(automations_dir, filename)
        try:
            with open(filepath) as f:
                payload = json.load(f)
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            continue

        print(f"Deploying {filename}...")
        try:
            resp = requests.post(BASE_URL, headers=HEADERS, json=payload, timeout=5.0)
            if resp.status_code == 201:
                data = resp.json()
                print(f" -> Created successfully: ID {data.get('id')}")
                success_count += 1
            else:
                print(f" -> Failed to create: HTTP {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f" -> Failed request: {e}")

    print(f"\nDeployment complete. {success_count} automations deployed.")


if __name__ == "__main__":
    main()
