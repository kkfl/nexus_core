import urllib.request, json, time, sys, os
head_sha = os.popen('git log -n 1 --format="%H"').read().strip().strip('"')
print(f"Polling CI for commit: {head_sha}")
url = f"https://api.github.com/repos/kkfl/nexus_core/commits/{head_sha}/check-runs"
for i in range(30):
    print(f"--- Poll {i+1} ---")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        res = json.loads(urllib.request.urlopen(req).read())
        runs = res.get("check_runs", [])
        if not runs:
            print("No runs yet...")
            time.sleep(10)
            continue
        all_done = True
        has_failure = False
        for cr in runs:
            status = cr["status"]
            conclusion = cr["conclusion"] or "pending"
            print(f"  {cr['name']}: {status} ({conclusion})")
            if status != "completed":
                all_done = False
            if cr["conclusion"] in ["failure", "cancelled", "timed_out"]:
                has_failure = True
        if all_done or has_failure:
            print("\n--- FINAL STATUS ---")
            if has_failure:
                # print annotations for failed runs
                for cr in runs:
                    if cr["conclusion"] == "failure":
                        ar = urllib.request.Request(
                            f"https://api.github.com/repos/kkfl/nexus_core/check-runs/{cr['id']}/annotations",
                            headers={"User-Agent": "Mozilla/5.0"}
                        )
                        anns = json.loads(urllib.request.urlopen(ar).read())
                        print(f"\nFailed: {cr['name']}")
                        for a in anns:
                            print(f"  {a['path']}:{a['start_line']} - {a['message']}")
                sys.exit(1)
            else:
                print("ALL JOBS PASSED! CI IS GREEN!")
                sys.exit(0)
        time.sleep(10)
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)
print("Timed out waiting for CI")
sys.exit(2)
