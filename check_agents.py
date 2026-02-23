import asyncio
import httpx

REGISTRY_URL = "http://agent-registry:8012/v1"
HEADERS = {"X-Service-ID": "admin", "X-Agent-Key": "admin-registry-key"}

async def check_agent(client, agent_name, base_url):
    results = {"name": agent_name, "url": base_url, "healthz": None, "readyz": None, "capabilities": None}
    
    # 1. Healthz
    try:
        r = await client.get(f"{base_url}/healthz", timeout=3.0)
        results["healthz"] = f"{r.status_code} {r.text[:50]}"
    except Exception as e:
        results["healthz"] = f"Error: {e}"

    # 2. Readyz
    try:
        r = await client.get(f"{base_url}/readyz", timeout=3.0)
        results["readyz"] = f"{r.status_code} {r.text[:50]}"
    except Exception as e:
        results["readyz"] = f"Error: {e}"

    # 3. Capabilities
    try:
        r = await client.get(f"{base_url}/capabilities", headers=HEADERS, timeout=3.0)
        if r.status_code == 200:
            results["capabilities"] = f"Yes ({len(str(r.json()))} chars)"
        elif r.status_code == 404:
            results["capabilities"] = "404 Not Found"
        else:
            results["capabilities"] = f"{r.status_code}"
    except Exception as e:
        results["capabilities"] = f"Error: {e}"

    return results

async def main():
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{REGISTRY_URL}/agents", headers=HEADERS)
        agents = res.json()
        
        tasks = []
        for a in agents:
            deps_res = await client.get(f"{REGISTRY_URL}/deployments?agent_id={a['id']}", headers=HEADERS)
            deps = deps_res.json()
            for d in deps:
                tasks.append(check_agent(client, a["name"], d["base_url"]))
                
        results = await asyncio.gather(*tasks)
        
        print(f"{'Agent':<20} | {'Healthz':<25} | {'Readyz':<25} | {'Capabilities'}")
        print("-" * 90)
        for r in results:
            h = r['healthz'].replace('\n', '')
            rd = r['readyz'].replace('\n', '')
            c = r['capabilities'].replace('\n', '')
            print(f"{r['name']:<20} | {h:<25} | {rd:<25} | {c}")

if __name__ == "__main__":
    asyncio.run(main())
