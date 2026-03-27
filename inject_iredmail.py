import sys
import httpx

def main():
    base_url = "http://localhost:8000"
    client = httpx.Client(base_url=base_url)

    # Login
    resp = client.post(
        "/auth/login", data={"username": "admin@nexus.local", "password": "admin_password"}
    )
    if resp.status_code != 200:
        print("Login failed:", resp.text)
        sys.exit(1)

    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})

    secrets = [
        {
            "alias": "ssh.iredmail.host",
            "tenant_id": "nexus-core",
            "env": "prod",
            "value": "mx.gsmcall.com",
            "description": "iRedMail SSH Host",
            "rotation_interval_days": 180,
        },
        {
            "alias": "ssh.iredmail.port",
            "tenant_id": "nexus-core",
            "env": "prod",
            "value": "2007",
            "description": "iRedMail SSH Port",
            "rotation_interval_days": 180,
        },
        {
            "alias": "ssh.iredmail.username",
            "tenant_id": "nexus-core",
            "env": "prod",
            "value": "root",
            "description": "iRedMail SSH Username",
            "rotation_interval_days": 180,
        },
        {
            "alias": "ssh.iredmail.private_key_pem",
            "tenant_id": "nexus-core",
            "env": "prod",
            "value": "G$Mcall01",
            "description": "iRedMail SSH Password (Fallback)",
            "rotation_interval_days": 180,
        }
    ]

    for sec in secrets:
        resp = client.post("/portal/secrets", json=sec)
        if resp.status_code == 201:
            print(f"Created secret: {sec['alias']}")
        elif resp.status_code == 409:
            print(f"Secret exists, patching: {sec['alias']}")
            # Find the ID to patch
            list_resp = client.get("/portal/secrets")
            sec_id = None
            for existing in list_resp.json():
                if existing["alias"] == sec["alias"]:
                    sec_id = existing["id"]
                    break
            if sec_id:
                patch_resp = client.patch(f"/portal/secrets/{sec_id}", json={"value": sec["value"]})
                print(f"Patched {sec['alias']}: {patch_resp.status_code}")
        else:
            print(f"Failed to create {sec['alias']}: {resp.status_code} {resp.text}")

if __name__ == "__main__":
    main()
