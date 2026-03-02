import requests

login = requests.post(
    "http://localhost:8000/auth/login",
    data={"username": "admin@nexus.local", "password": "admin_password"},
)
token = login.json()["access_token"]

# fetch the secret first so we know the correct ID
secrets = requests.get(
    "http://localhost:8000/portal/secrets",
    params={"env": "dev"},
    headers={"Authorization": f"Bearer {token}"},
).json()
secret_id = next(s["id"] for s in secrets if s["alias"] == "dns.dnsmadeeasy.api_key")

resp = requests.patch(
    f"http://localhost:8000/portal/secrets/{secret_id}",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "alias": "dns.dnsmadeeasy.api_key_updated",
        "env": "stage",
        "value": "completely_new_value",
    },
)
print("Status:", resp.status_code)
print("Response:", resp.text)
