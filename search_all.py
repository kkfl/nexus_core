import os

files_to_check = [
    "debug_secrets.json",
    "secrets_logs.txt",
    "secrets_logs_utf8.txt",
    "registry_snapshot.txt"
]
for p in files_to_check:
    print(f"--- {p} ---")
    try:
        with open(p, "rb") as f:
            content = f.read()
            # Try utf-8
            try:
                decoded = content.decode("utf-8")
            except UnicodeDecodeError:
                # Try utf-16
                decoded = content.decode("utf-16")
            
            # Print if not too large, or print lines matching vultr, telegram, smtp
            for line in decoded.splitlines():
                lmatch = line.lower()
                if "telegram" in lmatch or "vultr" in lmatch or "smtp" in lmatch or "proxmox" in lmatch or "smtp" in lmatch:
                    print(line)
    except Exception as e:
        print(f"Error {p}: {e}")
