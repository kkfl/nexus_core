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
            "alias": "db.postgres.master",
            "tenant_id": "nexus-core",
            "env": "prod",
            "value": "Sup3rS3cr3tP@ssw0rd!",
            "description": "Production Postgres Master Password",
            "rotation_interval_days": 90,
        },
        {
            "alias": "api.stripe.key",
            "tenant_id": "nexus-payments",
            "env": "prod",
            "value": "REPLACE_ME_stripe_test_key",
            "description": "Stripe Live API Key",
            "rotation_interval_days": 180,
        },
        {
            "alias": "twilio.auth.token",
            "tenant_id": "nexus-communications",
            "env": "prod",
            "value": "twilio-auth-token-987654321",
            "description": "Twilio Communication API Token",
            "rotation_interval_days": 30,
        },
        {
            "alias": "smtp.mailgun.password",
            "tenant_id": "nexus-notifications",
            "env": "dev",
            "value": "dev-smtp-mailgun-password",
            "description": "Development Mailgun Password",
            "rotation_interval_days": 60,
        },
        {
            "alias": "aws.s3.secret_key",
            "tenant_id": "nexus-storage",
            "env": "stage",
            "value": "aws-secret-access-key-stage",
            "description": "AWS S3 Secret Key for Staging",
            "rotation_interval_days": 90,
        },
    ]

    for sec in secrets:
        resp = client.post("/api/portal/secrets", json=sec)
        if resp.status_code == 201:
            print(f"Created secret: {sec['alias']}")
        elif resp.status_code == 409:
            print(f"Secret exists: {sec['alias']}")
        else:
            print(f"Failed to create {sec['alias']}: {resp.status_code} {resp.text}")


if __name__ == "__main__":
    main()
