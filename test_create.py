import requests

login = requests.post(
    "http://localhost:8000/auth/login",
    data={"username": "admin@nexus.local", "password": "admin_password"},
)
token = login.json()["access_token"]

resp = requests.post(
    "http://localhost:8000/portal/secrets",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "alias": "dns.dnsmadeeasy.api_key_updated",
        "tenant_id": "nexus",
        "env": "stage",
        "value": "completely_new_value",
        "description": "testing",
        "rotation_interval_days": None,
    },
)
print("Create Status:", resp.status_code)
print("Create Response:", resp.text)
