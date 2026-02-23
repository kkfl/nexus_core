import urllib.request, json, time, sys, os
head_sha = os.popen('git log -n 1 --format="%H"').read().strip()
url = f"https://api.github.com/repos/kkfl/nexus_core/commits/{head_sha}/check-runs"
for i in range(30):
    print(f"--- Poll {i} for {head_sha} ---")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = json.loads(urllib.request.urlopen(req).read())
        runs = res.get('check_runs', [])
        if not runs:
            print("No runs found yet...")
            time.sleep(10)
            continue
        all_completed = True
        has_failure = False
        for cr in runs:
            print(f"{cr['name']}: {cr['status']} - {cr['conclusion']}")
            if cr['status'] != 'completed':
                all_completed = False
            if cr['conclusion'] in ['failure', 'cancelled', 'timed_out']:
                has_failure = True
        if all_completed or has_failure:
            print("\nFINISHED POLLING.")
            sys.exit(0 if not has_failure else 1)
        print("Waiting...")
    except Exception as e:
        print("Error", e)
    time.sleep(10)
