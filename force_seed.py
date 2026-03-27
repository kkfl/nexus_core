import httpx
import sys

HEADERS = {
    "X-Service-ID": "nexus",
    "X-Agent-Key": "nexus-internal-key",
    "Content-Type": "application/json"
}

try:
    with httpx.Client() as client:
        p1 = {
            "alias": "telegram.bot_token",
            "tenant_id": "nexus",
            "env": "prod",
            "value": "8601739749:AAEYAZC7cT_M7wFAdT19dV4hZswJncgy9TM",
            "description": "Bot Token"
        }
        r = client.post("http://localhost:8007/v1/secrets", json=p1, headers=HEADERS)
        print("Bot Token:", r.status_code, r.text)

        p2 = {
            "alias": "telegram.default_chat_id",
            "tenant_id": "nexus",
            "env": "prod",
            "value": "8289774894",
            "description": "Chat ID"
        }
        r2 = client.post("http://localhost:8007/v1/secrets", json=p2, headers=HEADERS)
        print("Chat ID:", r2.status_code, r2.text)
except Exception as e:
    print("Error:", e)
