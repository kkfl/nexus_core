import urllib.request, json
res = json.loads(urllib.request.urlopen('https://api.github.com/repos/kkfl/nexus_core/commits/05bc072a6536731d288df5cb15cf11507b00f4da/check-runs').read())
for c in res.get('check_runs', []):
    if c['status'] == 'completed':
        req = urllib.request.Request(f'https://api.github.com/repos/kkfl/nexus_core/check-runs/{c["id"]}/annotations', headers={'User-Agent': 'Mozilla/5.0'})
        anns = json.loads(urllib.request.urlopen(req).read())
        for a in anns:
            print(f"{c['name']} - {a['path']}:{a['start_line']} - {a['message']}")
