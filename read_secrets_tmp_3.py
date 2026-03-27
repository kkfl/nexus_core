import json

try:
    with open('debug_secrets.json', 'r', encoding='utf-16') as f:
        data = json.load(f)
    found = False
    for secret in data:
        if 'telegram' in secret.get('alias', '').lower():
            print(f"FOUND: {secret['alias']} = {secret['value']}")
            found = True
    if not found:
        print("No telegram secrets found in debug_secrets.json")
except Exception as e:
    print(f"Error parsing json: {e}")
