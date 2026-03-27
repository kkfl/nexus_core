import gzip
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from packages.shared.secrets import decrypt_secret
except ImportError as e:
    print("Missing python packages:", e)
    sys.exit(1)

master_key = "Lq/rV+W5s7/V+8S3c5jGZ8s/8i8e6yGZ8s/8i8e6yGY="
backup_file = os.path.join(os.path.dirname(__file__), "nexus_backup_2026-03-20_1649.sql.gz")

try:
    with gzip.open(backup_file, "rt", encoding="utf-8") as f:
        in_secrets = False
        print("--- Recovered Legacy Secrets (No Filters) ---")
        for line in f:
            if line.startswith("COPY public.secrets "):
                in_secrets = True
                continue
            if in_secrets:
                if line.startswith("\\."):
                    in_secrets = False
                    break
                
                parts = line.split("\t")
                if len(parts) >= 6:
                    name = parts[1]
                    owner_type = parts[2]
                    purpose = parts[4]
                    enc_val = parts[5]
                    
                    try:
                        decrypted = decrypt_secret(enc_val, master_key)
                        print(f"Name/Alias: {name} | Owner: {owner_type} | Purpose: {purpose}")
                        print(f"Value: {decrypted}")
                        print("-" * 30)
                    except Exception as e:
                        print(f"Failed to decrypt {name}: {e}")
except Exception as e:
    print(f"Error reading backup: {e}")
