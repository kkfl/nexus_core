import gzip
import os
import sys

# Add local packages folder to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from packages.shared.secrets import decrypt_secret
except ImportError as e:
    print("Missing python packages:", e)
    sys.exit(1)

master_key = "Lq/rV+W5s7/V+8S3c5jGZ8s/8i8e6yGZ8s/8i8e6yGY="

backup_file = os.path.join(os.path.dirname(__file__), "nexus_backup_2026-03-23_1424.sql.gz")

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
                
                parts = line.split("\t")
                if len(parts) >= 5:
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
