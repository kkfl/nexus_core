import gzip
import os
import glob

# Search all unencrypted backups for the word "secrets"
backup_dir = os.path.dirname(__file__)
for backup_file in glob.glob(os.path.join(backup_dir, "*.sql.gz")):
    print(f"Checking {os.path.basename(backup_file)} ...")
    try:
        with gzip.open(backup_file, "rt", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if line.startswith("COPY public.secrets "):
                    print(f"  Line {i}: {line[:100].strip()}")
                elif "telegram" in line.lower() and "secrets" in line.lower():
                    print(f"  Line {i}: {line.strip()}")
    except Exception as e:
        print("  Error:", e)
