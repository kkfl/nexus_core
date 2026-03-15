"""
Quick smoke test for email-agent endpoints (runs inside Docker container).
"""

import json
import urllib.request

BASE = "http://localhost:8014"
HEADERS = {"X-Service-ID": "nexus", "X-Agent-Key": "nexus-email-key-change-me"}


def get(path):
    req = urllib.request.Request(f"{BASE}{path}", headers=HEADERS)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)[:200]}


def post(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=body,
        headers={**HEADERS, "Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)[:200]}


if __name__ == "__main__":
    print("=" * 60)
    print("Email Agent Smoke Test")
    print("=" * 60)

    # 1. healthz
    print("\n1. /healthz")
    r = get("/healthz")
    print(f"   {r}")

    # 2. Health check
    print("\n2. /email/health")
    r = get("/email/health")
    print(f"   SMTP:  {r.get('smtp')} {r.get('smtp_detail', '')}")
    print(f"   IMAP:  {r.get('imap')} {r.get('imap_detail', '')}")
    print(f"   SSH:   {r.get('ssh_bridge')} {r.get('ssh_detail', '')}")

    # 3. Test send
    print("\n3. /email/test_send")
    r = post(
        "/email/test_send",
        {
            "to": "alerts@gsmcall.com",
            "subject": "Email Agent Smoke Test",
            "body_text": "Automated smoke test from Nexus Email Agent",
        },
    )
    print(f"   ok={r.get('ok')} msg_id={(r.get('message_id') or '')[:40]} err={r.get('error', '')}")

    # 4. Admin mailbox list
    print("\n4. /email/admin/mailbox/list")
    r = get("/email/admin/mailbox/list")
    if isinstance(r, list):
        print(f"   Count: {len(r)}")
        for m in [x for x in r if "nexus" in x.get("email", "")][:3]:
            print(f"   {m['email']} active={m['active']}")
    else:
        print(f"   {r}")

    # 5. Capabilities
    print("\n5. /v1/capabilities")
    r = get("/v1/capabilities")
    print(f"   {r.get('service')}: {len(r.get('capabilities', []))} capabilities")

    print("\n" + "=" * 60)
    print("DONE")
