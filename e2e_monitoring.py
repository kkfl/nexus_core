import asyncio
import json

import httpx

base_url = "http://localhost:8004"
headers = {"X-Service-ID": "admin", "X-Agent-Key": "admin-monitoring-key-change-me"}


async def run_all_green():
    print("--- Running ALL GREEN Test ---")
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Sync targets
        print("1. Syncing targets from registry...")
        resp = await client.post(f"{base_url}/v1/targets/sync-from-registry", headers=headers)
        print(f"Sync status: {resp.status_code}")

        # 2. List targets to verify
        print("2. Verifying targets exist...")
        resp = await client.get(f"{base_url}/v1/targets", headers=headers)
        targets = resp.json()
        print(f"Found {len(targets)} targets.")

        # 3. Run Checks
        print("3. Running active health checks...")
        resp = await client.post(f"{base_url}/v1/check/run", headers=headers)
        res = resp.json()
        print(f"Check results: {json.dumps(res, indent=2)}")

        # 4. Assert All UP
        print("4. Fetching current status...")
        resp = await client.get(f"{base_url}/v1/status/current", headers=headers)
        status = resp.json()
        all_up = all(
            [
                s["state"] == "UP"
                for s in status
                if s["agent_name"]
                in ["agent-registry", "secrets-agent", "notifications-agent", "monitoring-agent"]
            ]
        )

        if all_up:
            print("SUCCESS: All core agents are UP.")
        else:
            print("FAILURE: Some agents are not UP.")
            for s in status:
                print(f"  {s['agent_name']}: {s['state']}")
        return all_up


if __name__ == "__main__":
    asyncio.run(run_all_green())
