import json

import requests

login = requests.post(
    "http://localhost:8000/auth/login",
    data={"username": "admin@nexus.local", "password": "admin_password"},
)
token = login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
resp = requests.post(
    "http://localhost:8000/portal/secrets",
    headers=headers,
    json={
        "alias": "test.delete.secret.130",
        "tenant_id": "nexus",
        "env": "dev",
        "value": "temporary_value",
    },
)
secret_id = resp.json()["id"]

resp_valid = requests.delete(
    f"http://localhost:8000/portal/secrets/{secret_id}",
    headers=headers,
    json={"password": "admin_password", "reason": "Testing Break-Glass Delete Sequence"},
)
print(json.dumps(resp_valid.json(), indent=2))
