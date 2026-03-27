import urllib.request
import json
req = urllib.request.Request('http://localhost:8007/v1/secrets?tenant_id=nexus&env=prod')
req.add_header('X-Service-ID', 'nexus')
req.add_header('X-Agent-Key', 'nexus-internal-key')
data = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))
for x in data:
    if 'telegram' in x['alias']:
        print('Deleting', x['id'], x['alias'])
        try:
            r2 = urllib.request.Request(f"http://localhost:8007/v1/secrets/{x['id']}", method='DELETE')
            r2.add_header('X-Service-ID', 'nexus')
            r2.add_header('X-Agent-Key', 'nexus-internal-key')
            urllib.request.urlopen(r2)
            print('Success')
        except Exception as e:
            print('Fail:', e)
