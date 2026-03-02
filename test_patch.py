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
        "alias": "test.delete.secret.132",
        "tenant_id": "nexus",
        "env": "dev",
        "value": "temporary_value",
    },
)
secret_id = resp.json()["id"]

print("Created:", secret_id)
patch_resp = requests.patch(
    f"http://localhost:8000/portal/secrets/{secret_id}",
    headers=headers,
    json={"alias": "test.delete.secret.150"},
)
print("Patch Status:", patch_resp.status_code)
print("Patch Response:", patch_resp.text)
