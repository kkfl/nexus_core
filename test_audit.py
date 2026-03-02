import requests

login = requests.post(
    "http://localhost:8000/auth/login",
    data={"username": "admin@nexus.local", "password": "admin_password"},
)
token = login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

resp = requests.get("http://localhost:8000/portal/secrets/audit", headers=headers)
print("Status:", resp.status_code)
print("Audit Logs Length:", len(resp.json()) if resp.status_code == 200 else resp.text)
if resp.status_code == 200 and len(resp.json()) > 0:
    for event in resp.json()[:5]:
        print(event["action"], event["secret_alias"], event["result"])
