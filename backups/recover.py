import gzip
import os
import sys

# Must run inside nexus-api container where packages are installed
sys.path.insert(0, "/app")

from packages.shared.secrets import decrypt_secret

master_key = os.getenv("NEXUS_MASTER_KEY")
if not master_key:
    print("NEXUS_MASTER_KEY not found in environment")
    sys.exit(1)

backup_file = "/backups/nexus_backup_2026-03-23_1424.sql.gz"

try:
    with gzip.open(backup_file, "rt", encoding="utf-8") as f:
        in_secrets = False
        print("--- Recovered Secrets ---")
        for line in f:
            if line.startswith("COPY public.portal_secrets"):
                in_secrets = True
                continue
            if in_secrets:
                if line.startswith("\\."):
                    in_secrets = False
                    break
                
                # columns based on typical pg_dump: 
                # id, alias, tenant_id, env, value, key_version, description, scope_tags, created_at, updated_at, last_used_at, created_by
                parts = line.split("\t")
                if len(parts) >= 5:
                    # id = parts[0]
                    alias = parts[1]
                    tenant_id = parts[2]
                    env = parts[3]
                    enc_val = parts[4]
                    
                    try:
                        decrypted = decrypt_secret(enc_val, master_key)
                        print(f"Alias: {alias} | Tenant: {tenant_id} | Env: {env}")
                        print(f"Value: {decrypted}")
                        print("-" * 30)
                    except Exception as e:
                        print(f"Failed to decrypt {alias}: {e}")
except Exception as e:
    print(f"Error reading backup: {e}")
