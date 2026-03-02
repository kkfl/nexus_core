import requests

login = requests.post(
    "http://localhost:8000/auth/login",
    data={"username": "admin@nexus.local", "password": "admin_password"},
)
token = login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 1. Create a throwaway secret
resp = requests.post(
    "http://localhost:8000/portal/secrets",
    headers=headers,
    json={
        "alias": "test.delete.secret.125",
        "tenant_id": "nexus",
        "env": "dev",
        "value": "temporary_value",
    },
)
print("Create Status:", resp.status_code)
secret_id = resp.json()["id"]

# 2. Try to delete without password/reason (Should Fail 422)
resp_invalid = requests.delete(f"http://localhost:8000/portal/secrets/{secret_id}", headers=headers)
print("Invalid Delete Status (Expect 422):", resp_invalid.status_code)

# 3. Try to delete with wrong password (Should Fail 401)
resp_wrong_pw = requests.delete(
    f"http://localhost:8000/portal/secrets/{secret_id}",
    headers=headers,
    json={"password": "wrong_password", "reason": "Testing bad password"},
)
print("Unauthorized Delete Status (Expect 401):", resp_wrong_pw.status_code, resp_wrong_pw.text)

# 4. Try to delete with correct password and reason
resp_valid = requests.delete(
    f"http://localhost:8000/portal/secrets/{secret_id}",
    headers=headers,
    json={"password": "admin_password", "reason": "Testing Break-Glass Delete Sequence"},
)
print("Valid Delete Status (Expect 204):", resp_valid.status_code, resp_valid.text)
