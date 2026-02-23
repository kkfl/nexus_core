import urllib.request
import json

req = urllib.request.Request('https://api.github.com/repos/kkfl/nexus_core/commits/960ba39/check-runs', headers={'User-Agent': 'Mozilla/5.0'})
res = json.loads(urllib.request.urlopen(req).read())
for cr in res['check_runs']:
    if cr['conclusion'] == 'failure':
        print(f"\n--- {cr['name']} ---")
        out = cr.get('output', {})
        print(out.get('title', 'No Title'))
        print(out.get('summary', 'No Summary'))
        # Also let's try to get annotations if any
        ann_req = urllib.request.Request(f"https://api.github.com/repos/kkfl/nexus_core/check-runs/{cr['id']}/annotations", headers={'User-Agent': 'Mozilla/5.0'})
        try:
            annotations = json.loads(urllib.request.urlopen(ann_req).read())
            for ann in annotations:
                print(f"Annotation: {ann['path']}:{ann['start_line']} - {ann['message']}")
        except Exception as e:
            print(f"Could not get annotations: {e}")
