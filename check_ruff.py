import subprocess, json
res = subprocess.run(['python', '-m', 'ruff', 'check', 'scripts/fix_admin_vault_policy.py', 'scripts/fix_automation_vault_policy.py', 'scripts/fix_monitoring_auth.py', 'scripts/seed_monitoring_secret.py', 'scripts/deploy_automations.py', 'scripts/verify_automations.py', 'apps/monitoring_agent/api/status.py', '--output-format', 'json'], capture_output=True, text=True)
for e in json.loads(res.stdout):
    print(f"{e['filename']}:{e['location']['row']} - {e['code']} {e['message']}")
