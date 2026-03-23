"""
Backup & Restore router — Settings → Backup & Restore (admin-only)

  POST /run             — trigger a new pg_dump backup → .sql.gz
  GET  /list            — list available backups
  GET  /download/{fn}   — stream-download a backup file
  DELETE /{fn}          — remove a backup file
  POST /restore/{fn}    — **break-glass** restore (requires confirm="RESTORE")
  POST /upload-restore  — **break-glass** upload + restore from external file
  GET  /config          — get backup config (path, retention)
  PUT  /config          — update backup config
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from apps.nexus_api.dependencies import RequireRole

logger = structlog.get_logger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/backups"))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

_CONFIG_FILE = BACKUP_DIR / ".backup_config.json"
_ENV_FILE = Path("/app/.env") if Path("/app/.env").exists() else None
_DEFAULT_CONFIG = {
    "backup_dir": str(BACKUP_DIR),
    "max_backups": 10,
}


def _load_config() -> dict:
    if _CONFIG_FILE.exists():
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    return dict(_DEFAULT_CONFIG)


def _save_config(cfg: dict):
    with open(_CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def _read_env_value(key: str, default: str = "") -> str:
    """Read a value from the mounted .env file."""
    if not _ENV_FILE or not _ENV_FILE.exists():
        return os.environ.get(key, default)
    with open(_ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return os.environ.get(key, default)


def _write_env_value(key: str, value: str) -> bool:
    """Update a value in the mounted .env file. Returns True if changed."""
    if not _ENV_FILE or not _ENV_FILE.exists():
        logger.warning("env_file_not_mounted", path=str(_ENV_FILE))
        return False

    lines = _ENV_FILE.read_text().splitlines(keepends=True)
    found = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        # Append the key
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{key}={value}\n")

    _ENV_FILE.write_text("".join(new_lines))
    logger.info("env_value_updated", key=key, value=value)
    return True


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BackupInfo(BaseModel):
    filename: str
    size_bytes: int
    size_human: str
    created_at: str
    tables_included: str
    location: str = "default"
    encrypted: bool = False


class RunBackupRequest(BaseModel):
    subdirectory: str | None = None
    password: str | None = None


class BackupConfigIn(BaseModel):
    max_backups: int | None = None
    default_location: str | None = None


class BackupConfigOut(BaseModel):
    backup_dir: str
    backup_host_dir: str
    max_backups: int
    backup_count: int
    default_location: str
    locations: list[str]
    pending_restart: bool = False


class RestoreRequest(BaseModel):
    confirm: str
    password: str | None = None


class BackupResult(BaseModel):
    success: bool
    filename: str | None = None
    size_human: str | None = None
    location: str | None = None
    error: str | None = None


class RestoreResult(BaseModel):
    success: bool
    backup_used: str
    safety_backup: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def _pg_env() -> dict[str, str]:
    """Build environment dict for pg_dump/psql."""
    return {
        **os.environ,
        "PGHOST": os.environ.get("POSTGRES_HOST", "postgres"),
        "PGPORT": os.environ.get("POSTGRES_PORT", "5432"),
        "PGUSER": os.environ.get("POSTGRES_USER", "nexus"),
        "PGPASSWORD": os.environ.get("POSTGRES_PASSWORD", "nexus_pass"),
        "PGDATABASE": os.environ.get("POSTGRES_DB", "nexus_core"),
    }


def _resolve_backup_dir(subdirectory: str | None = None) -> Path:
    """Resolve backup target directory, with optional subdirectory."""
    if not subdirectory or subdirectory in ("default", "/", "."):
        return BACKUP_DIR
    # Sanitize: prevent path traversal
    clean = Path(subdirectory).name  # only take the last path component
    target = BACKUP_DIR / clean
    target.mkdir(parents=True, exist_ok=True)
    return target


def _list_locations() -> list[str]:
    """List available backup subdirectories."""
    locations = ["default"]
    for d in sorted(BACKUP_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            locations.append(d.name)
    return locations


def _list_backups() -> list[BackupInfo]:
    """Scan backup directory and subdirectories for .sql.gz and .sql.gz.enc files."""
    backups = []

    def _scan_dir(directory: Path, location: str):
        # Both .sql.gz and .sql.gz.enc
        for pattern in ("nexus_backup_*.sql.gz", "nexus_backup_*.sql.gz.enc"):
            for f in sorted(directory.glob(pattern), reverse=True):
                stat = f.stat()
                is_enc = f.name.endswith(".enc")
                # Strip extensions to get date
                base = f.name
                for ext in (".enc", ".sql.gz", ".sql"):
                    base = base.replace(ext, "")
                date_str = base.replace("nexus_backup_", "")
                backups.append(
                    BackupInfo(
                        filename=f.name,
                        size_bytes=stat.st_size,
                        size_human=_human_size(stat.st_size),
                        created_at=date_str,
                        tables_included="all (full database)",
                        location=location,
                        encrypted=is_enc,
                    )
                )

    # Scan root
    _scan_dir(BACKUP_DIR, "default")
    # Scan subdirectories
    for subdir in sorted(BACKUP_DIR.iterdir()):
        if subdir.is_dir() and not subdir.name.startswith("."):
            _scan_dir(subdir, subdir.name)
    # Sort all by date descending
    backups.sort(key=lambda b: b.created_at, reverse=True)
    return backups


async def _enforce_retention():
    """Delete oldest backups if over retention limit."""
    cfg = _load_config()
    max_backups = cfg.get("max_backups", 10)
    backups = _list_backups()
    if len(backups) > max_backups:
        removed = []
        for old in backups[max_backups:]:
            path = BACKUP_DIR / old.filename
            if path.exists():
                path.unlink()
                removed.append(old.filename)
                logger.info("backup_rotated", filename=old.filename)
        if removed:
            from apps.nexus_api.notify import notify_action

            await notify_action(
                action="backup.retention",
                subject="\U0001f9f9 Backup Retention Cleanup",
                body=f"Removed {len(removed)} old backup(s): {', '.join(removed[:3])}",
                event_type="nexus.backup.retention",
                payload={"removed_count": len(removed), "max_backups": max_backups},
            )


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

_backup_progress: dict = {
    "active": False,
    "stage": "idle",  # idle | counting | dumping | compressing | encrypting | done | error
    "current_table": "",
    "tables_done": 0,
    "tables_total": 0,
    "message": "",
}

_TABLE_DATA_RE = re.compile(
    r'(?:dumping contents of|saving data for) table "(?:public\.)?(.+?)"', re.IGNORECASE
)


def _reset_progress():
    _backup_progress.update(
        active=False,
        stage="idle",
        current_table="",
        tables_done=0,
        tables_total=0,
        message="",
    )


def _set_progress(stage: str, message: str = "", **kwargs):
    _backup_progress["active"] = stage not in ("idle", "done", "error")
    _backup_progress["stage"] = stage
    if message:
        _backup_progress["message"] = message
    _backup_progress.update(kwargs)


# Restore progress tracking
_restore_progress: dict = {
    "active": False,
    "stage": "idle",
    "current_table": "",
    "tables_done": 0,
    "tables_total": 0,
    "message": "",
}

_COPY_RE = re.compile(r'^COPY\s+(?:public\.)?"?([\w]+)"?\s', re.IGNORECASE)


def _reset_restore_progress():
    _restore_progress.update(
        active=False,
        stage="idle",
        current_table="",
        tables_done=0,
        tables_total=0,
        message="",
    )


def _set_restore_progress(stage: str, message: str = "", **kwargs):
    _restore_progress["active"] = stage not in ("idle", "done", "error")
    _restore_progress["stage"] = stage
    if message:
        _restore_progress["message"] = message
    _restore_progress.update(kwargs)


def _count_copy_statements(sql_path) -> int:
    """Count COPY statements in a SQL file to estimate restore table count."""
    count = 0
    with open(sql_path, errors="replace") as f:
        for line in f:
            if _COPY_RE.match(line):
                count += 1
    return count


async def _run_psql_tracked(raw_path, env: dict) -> tuple[int, str]:
    """Run psql feeding SQL line-by-line, tracking COPY statements for progress."""
    total = _count_copy_statements(raw_path)
    _set_restore_progress(
        "restoring", message="Starting restore...", tables_total=total, tables_done=0
    )

    proc = await asyncio.create_subprocess_exec(
        "psql",
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    tables_done = 0

    # Feed SQL file line-by-line through stdin
    with open(raw_path, "rb") as f:
        for line in f:
            proc.stdin.write(line)
            # Check for COPY statements
            try:
                text = line.decode("utf-8", "replace")
                m = _COPY_RE.match(text)
                if m:
                    tables_done += 1
                    table_name = m.group(1)
                    _set_restore_progress(
                        "restoring",
                        message=f"Restoring: {table_name}",
                        current_table=table_name,
                        tables_done=tables_done,
                    )
            except Exception:
                pass
            # Flush periodically to keep psql processing
            if tables_done % 5 == 0:
                try:
                    await proc.stdin.drain()
                except Exception:
                    break

    proc.stdin.close()
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=900)
    stderr_text = stderr.decode(errors="replace")[-500:] if stderr else ""

    return proc.returncode, stderr_text


# ---------------------------------------------------------------------------
# Core backup helper (used by endpoint + internal safety backup calls)
# ---------------------------------------------------------------------------


async def _count_tables(env: dict) -> int:
    """Count user tables in the database."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "psql",
            "-t",
            "-A",
            "-c",
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'",
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        return int(stdout.decode().strip())
    except Exception:
        return 0


async def _create_backup(
    subdirectory: str | None = None, password: str | None = None
) -> BackupResult:
    """Core backup logic — runs pg_dump and produces a gzipped SQL file, optionally encrypted."""
    cfg = _load_config()
    subdir = subdirectory or cfg.get("default_location")
    target_dir = _resolve_backup_dir(subdir)
    location_label = subdir if subdir and subdir not in ("default", "/", ".") else "default"

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M")
    base_filename = f"nexus_backup_{timestamp}.sql.gz"
    filename = f"{base_filename}.enc" if password else base_filename
    filepath = target_dir / filename
    gz_path = target_dir / base_filename
    raw_path = target_dir / f".tmp_{base_filename}.sql"

    try:
        env = _pg_env()

        # Count tables for progress
        _set_progress("counting", message="Counting database tables...")
        total_tables = await _count_tables(env)
        _set_progress(
            "dumping", message="Starting database dump...", tables_total=total_tables, tables_done=0
        )

        # Use --verbose to get per-table progress via stderr
        proc = await asyncio.create_subprocess_exec(
            "pg_dump",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--verbose",
            "-f",
            str(raw_path),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Read stderr line-by-line for progress
        tables_dumped = 0
        stderr_lines = []
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            text = line.decode(errors="replace").strip()
            stderr_lines.append(text)
            m = _TABLE_DATA_RE.search(text)
            if m:
                tables_dumped += 1
                table_name = m.group(1)
                _set_progress(
                    "dumping",
                    message=f"Dumping: {table_name}",
                    current_table=table_name,
                    tables_done=tables_dumped,
                )

        await asyncio.wait_for(proc.wait(), timeout=120)

        if proc.returncode != 0:
            err = "\n".join(stderr_lines[-5:])[:500]
            logger.error("backup_pg_dump_failed", error=err)
            _set_progress("error", message=f"pg_dump failed: {err}")
            return BackupResult(success=False, error=f"pg_dump failed: {err}")

        # Compress
        _set_progress("compressing", message="Compressing backup...")
        with open(raw_path, "rb") as f_in, gzip.open(gz_path, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)

        raw_path.unlink(missing_ok=True)

        # Encrypt if password provided
        if password:
            _set_progress("encrypting", message="Encrypting with AES-256...")
            from packages.shared.backup_crypto import encrypt_backup

            master_key = os.environ.get("NEXUS_MASTER_KEY", "")
            sql_gz_data = gz_path.read_bytes()
            encrypted = encrypt_backup(sql_gz_data, password, master_key)
            filepath.write_bytes(encrypted)
            gz_path.unlink(missing_ok=True)
            logger.info("backup_encrypted", filename=filename)

        size = filepath.stat().st_size
        _set_progress("done", message=f"Backup complete: {filename} ({_human_size(size)})")
        logger.info(
            "backup_created", filename=filename, size=_human_size(size), encrypted=bool(password)
        )

        await _enforce_retention()

        from apps.nexus_api.notify import notify_action

        await notify_action(
            action="backup.created",
            subject="\U0001f4be Backup Created" + (" 🔒" if password else ""),
            body=f"{filename} ({_human_size(size)})",
            event_type="nexus.backup.created",
            payload={"filename": filename, "size": _human_size(size), "encrypted": bool(password)},
        )

        return BackupResult(
            success=True,
            filename=filename,
            size_human=_human_size(size),
            location=location_label,
        )

    except TimeoutError:
        raw_path.unlink(missing_ok=True)
        gz_path.unlink(missing_ok=True)
        filepath.unlink(missing_ok=True)
        _set_progress("error", message="Backup timed out (120s)")
        return BackupResult(success=False, error="Backup timed out (120s)")
    except Exception as e:
        raw_path.unlink(missing_ok=True)
        gz_path.unlink(missing_ok=True)
        filepath.unlink(missing_ok=True)
        logger.error("backup_error", error=str(e))
        _set_progress("error", message=str(e))
        return BackupResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/run", response_model=BackupResult)
async def run_backup(
    body: RunBackupRequest | None = None,
    current_user: Any = Depends(RequireRole(["admin"])),
):
    """Trigger a new database backup (pg_dump → gzipped SQL, optionally encrypted)."""
    subdirectory = body.subdirectory if body else None
    password = body.password if body else None
    _reset_progress()
    return await _create_backup(subdirectory=subdirectory, password=password)


@router.get("/progress")
async def backup_progress(
    current_user: Any = Depends(RequireRole(["admin"])),
):
    """Return current backup progress for polling."""
    return dict(_backup_progress)


@router.get("/restore-progress")
async def restore_progress_endpoint(
    current_user: Any = Depends(RequireRole(["admin"])),
):
    """Return current restore progress for polling."""
    return dict(_restore_progress)


@router.get("/list", response_model=list[BackupInfo])
async def list_backups(
    current_user: Any = Depends(RequireRole(["admin"])),
):
    """List all available backups."""
    return _list_backups()


@router.get("/download/{filename}")
async def download_backup(
    filename: str,
    location: str | None = None,
    token: str | None = None,
):
    """Download a backup file. Auth via ?token=JWT query param for browser-native downloads."""
    # Validate the JWT token from query param
    if not token:
        raise HTTPException(status_code=401, detail="Token required (?token=JWT)")

    from jose import JWTError
    from jose import jwt as jose_jwt

    from packages.shared.config import settings

    try:
        payload = jose_jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Verify admin role
    from sqlalchemy.future import select

    from packages.shared.db import get_db_context
    from packages.shared.models import User

    async with get_db_context() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        if not user or user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

    # Resolve the backup directory (root or subdirectory)
    target_dir = _resolve_backup_dir(location)
    filepath = target_dir / filename
    if not filepath.exists() or not filepath.name.startswith("nexus_backup_"):
        # Also search all subdirectories as fallback
        filepath = BACKUP_DIR / filename
        if not filepath.exists():
            for subdir in BACKUP_DIR.iterdir():
                if subdir.is_dir():
                    candidate = subdir / filename
                    if candidate.exists():
                        filepath = candidate
                        break
            else:
                raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{filename}")
async def delete_backup(
    filename: str,
    location: str | None = None,
    current_user: Any = Depends(RequireRole(["admin"])),
):
    """Delete a backup file."""
    target_dir = _resolve_backup_dir(location)
    filepath = target_dir / filename
    if not filepath.exists() or not filepath.name.startswith("nexus_backup_"):
        # Search all directories as fallback
        filepath = BACKUP_DIR / filename
        if not filepath.exists():
            for subdir in BACKUP_DIR.iterdir():
                if subdir.is_dir():
                    candidate = subdir / filename
                    if candidate.exists():
                        filepath = candidate
                        break
            else:
                raise HTTPException(status_code=404, detail="Backup not found")
    filepath.unlink()
    logger.info("backup_deleted", filename=filename)

    from apps.nexus_api.notify import notify_action

    await notify_action(
        action="backup.deleted",
        subject="🗑️ Backup Deleted",
        body=filename,
        event_type="nexus.backup.deleted",
        payload={"filename": filename},
    )

    return {"deleted": filename}


@router.post("/restore/{filename}", response_model=RestoreResult)
async def restore_backup(
    filename: str,
    body: RestoreRequest,
    current_user: Any = Depends(RequireRole(["admin"])),
):
    """
    BREAK-GLASS RESTORE — requires confirm="RESTORE" in request body.
    Auto-creates a safety backup before restoring.
    Encrypted (.enc) backups require password.
    """
    if body.confirm != "RESTORE":
        raise HTTPException(
            status_code=400,
            detail='You must send {"confirm": "RESTORE"} to proceed.',
        )

    # Search all directories for the backup file
    filepath = BACKUP_DIR / filename
    if not filepath.exists():
        for subdir in BACKUP_DIR.iterdir():
            if subdir.is_dir():
                candidate = subdir / filename
                if candidate.exists():
                    filepath = candidate
                    break
    if not filepath.exists() or not filepath.name.startswith("nexus_backup_"):
        raise HTTPException(status_code=404, detail="Backup not found")

    is_encrypted = filepath.name.endswith(".enc")
    if is_encrypted and not body.password:
        raise HTTPException(
            status_code=400, detail="Password required to restore encrypted backup."
        )

    # Step 1: Auto-create safety backup of current state
    safety_result = await _create_backup()
    safety_filename = safety_result.filename if safety_result.success else None

    # Step 2: Decrypt (if encrypted), decompress, and restore
    try:
        raw_path = BACKUP_DIR / f".tmp_restore_{filename}.sql"

        _reset_restore_progress()
        if is_encrypted:
            _set_restore_progress("decrypting", message="Decrypting backup...")
        else:
            _set_restore_progress("decompressing", message="Decompressing backup...")

        if is_encrypted:
            from packages.shared.backup_crypto import decrypt_backup

            try:
                master_key, sql_gz_data = decrypt_backup(filepath.read_bytes(), body.password)
            except ValueError as e:
                _set_restore_progress("error", message=str(e))
                return RestoreResult(
                    success=False,
                    backup_used=filename,
                    safety_backup=safety_filename,
                    error=str(e),
                )
            # Decompress the decrypted gzip data
            import io

            with gzip.open(io.BytesIO(sql_gz_data), "rb") as f_in, open(raw_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            # Update NEXUS_MASTER_KEY in .env
            _write_env_value("NEXUS_MASTER_KEY", master_key)
            os.environ["NEXUS_MASTER_KEY"] = master_key
            logger.info("restore_master_key_updated", source=filename)
        else:
            with gzip.open(filepath, "rb") as f_in, open(raw_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        returncode, stderr_text = await _run_psql_tracked(raw_path, _pg_env())

        raw_path.unlink(missing_ok=True)

        if returncode != 0:
            logger.error("restore_failed", error=stderr_text)
            _set_restore_progress("error", message=f"psql restore failed: {stderr_text}")
            return RestoreResult(
                success=False,
                backup_used=filename,
                safety_backup=safety_filename,
                error=f"psql restore failed: {stderr_text}",
            )

        _set_restore_progress("done", message="Restore complete!")
        logger.info(
            "restore_success", filename=filename, safety=safety_filename, encrypted=is_encrypted
        )

        from apps.nexus_api.notify import notify_action

        await notify_action(
            action="backup.restored",
            subject="⚠️ Database Restored" + (" 🔒" if is_encrypted else ""),
            body=f"Restored from {filename} (safety backup: {safety_filename})",
            event_type="nexus.backup.restored",
            severity="warn",
            payload={"filename": filename, "safety_backup": safety_filename},
        )
        return RestoreResult(
            success=True,
            backup_used=filename,
            safety_backup=safety_filename,
        )

    except Exception as e:
        logger.error("restore_error", error=str(e))
        return RestoreResult(
            success=False,
            backup_used=filename,
            safety_backup=safety_filename,
            error=str(e),
        )


@router.post("/upload-restore", response_model=RestoreResult)
async def upload_and_restore(
    file: UploadFile = File(...),
    confirm: str = Form(...),
    password: str = Form(""),
    current_user: Any = Depends(RequireRole(["admin"])),
):
    """
    BREAK-GLASS UPLOAD & RESTORE — disaster recovery.
    Accepts a .sql.gz file upload. Creates a safety backup of the current
    database first, then restores from the uploaded file.
    Requires confirm="UPLOAD_RESTORE" as a form field.
    """
    import subprocess as _sp
    import time as _time

    t0 = _time.monotonic()
    logger.warning("TRACE upload_restore STEP-0 entry")

    if confirm != "UPLOAD_RESTORE":
        raise HTTPException(
            status_code=400,
            detail='You must send confirm="UPLOAD_RESTORE" to proceed.',
        )

    # Validate file
    valid_ext = file.filename and (
        file.filename.endswith(".sql.gz") or file.filename.endswith(".sql.gz.enc")
    )
    if not file.filename or not valid_ext:
        raise HTTPException(
            status_code=400,
            detail="File must be a .sql.gz or .sql.gz.enc backup file.",
        )
    is_encrypted = file.filename.endswith(".enc")
    if is_encrypted and not password:
        raise HTTPException(
            status_code=400, detail="Password required to restore encrypted backup."
        )

    # STEP 1: Save uploaded file
    upload_name = f"uploaded_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    upload_path = BACKUP_DIR / upload_name
    try:
        logger.warning(
            "TRACE upload_restore STEP-1 reading upload", elapsed=f"{_time.monotonic() - t0:.1f}s"
        )
        content = await file.read()
        # Validate file header: gzip magic (1f 8b) or NEXUS_ENC_V1 magic
        from packages.shared.backup_crypto import MAGIC as _ENC_MAGIC

        if content[:2] != b"\x1f\x8b" and not content[: len(_ENC_MAGIC)] == _ENC_MAGIC:
            raise HTTPException(
                status_code=400,
                detail="File does not appear to be a valid gzip or encrypted backup.",
            )
        with open(upload_path, "wb") as f:
            f.write(content)
        logger.warning(
            "TRACE upload_restore STEP-1 done",
            filename=upload_name,
            size=len(content),
            encrypted=is_encrypted,
            elapsed=f"{_time.monotonic() - t0:.1f}s",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

    # STEP 2: Safety backup of current state
    logger.warning(
        "TRACE upload_restore STEP-2 safety backup starting",
        elapsed=f"{_time.monotonic() - t0:.1f}s",
    )
    safety_result = await _create_backup()
    safety_filename = safety_result.filename if safety_result.success else None
    logger.warning(
        "TRACE upload_restore STEP-2 safety backup done",
        safety=safety_filename,
        elapsed=f"{_time.monotonic() - t0:.1f}s",
    )

    # STEP 3: Decompress
    raw_path = BACKUP_DIR / f".tmp_upload_restore_{upload_name}.sql"
    try:
        logger.warning(
            "TRACE upload_restore STEP-3 decompressing",
            encrypted=is_encrypted,
            elapsed=f"{_time.monotonic() - t0:.1f}s",
        )

        _reset_restore_progress()
        if is_encrypted:
            _set_restore_progress("decrypting", message="Decrypting backup...")
        else:
            _set_restore_progress("decompressing", message="Decompressing backup...")

        if is_encrypted:
            from packages.shared.backup_crypto import decrypt_backup

            try:
                master_key, sql_gz_data = decrypt_backup(upload_path.read_bytes(), password)
            except ValueError as e:
                upload_path.unlink(missing_ok=True)
                return RestoreResult(
                    success=False,
                    backup_used=upload_name,
                    safety_backup=safety_filename,
                    error=str(e),
                )
            import io

            with gzip.open(io.BytesIO(sql_gz_data), "rb") as f_in, open(raw_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            # Update NEXUS_MASTER_KEY in .env so vault secrets work after restore
            _write_env_value("NEXUS_MASTER_KEY", master_key)
            os.environ["NEXUS_MASTER_KEY"] = master_key
            logger.info("restore_master_key_updated", source=upload_name)
        else:
            with gzip.open(upload_path, "rb") as f_in, open(raw_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        raw_size = raw_path.stat().st_size
        logger.warning(
            "TRACE upload_restore STEP-3 done",
            sql_size=_human_size(raw_size),
            elapsed=f"{_time.monotonic() - t0:.1f}s",
        )

        # STEP 4: Terminate other DB connections to prevent lock contention
        #   The restore SQL has DROP CONSTRAINT / ALTER TABLE which need exclusive locks.
        #   The API's own connections (auth, heartbeats) hold conflicting locks.
        logger.warning(
            "TRACE upload_restore STEP-4 terminating other DB sessions",
            elapsed=f"{_time.monotonic() - t0:.1f}s",
        )
        env = _pg_env()

        # Kill all other connections to the database so psql can acquire exclusive locks
        kill_sql = "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = current_database() AND pid != pg_backend_pid();"
        _sp.run(
            ["psql", "-c", kill_sql],
            env=env,
            stdout=_sp.DEVNULL,
            stderr=_sp.DEVNULL,
            timeout=10,
        )
        logger.warning(
            "TRACE upload_restore STEP-4 sessions terminated",
            elapsed=f"{_time.monotonic() - t0:.1f}s",
        )

        # STEP 5: Run psql with progress tracking
        logger.warning(
            "TRACE upload_restore STEP-5 psql starting", elapsed=f"{_time.monotonic() - t0:.1f}s"
        )

        def _run_psql_sync():
            """Run psql synchronously with COPY tracking."""
            import subprocess as _sp2

            total = _count_copy_statements(raw_path)
            _set_restore_progress(
                "restoring", message="Starting restore...", tables_total=total, tables_done=0
            )

            proc = _sp2.Popen(
                ["psql"],
                env=env,
                stdin=_sp2.PIPE,
                stdout=_sp2.DEVNULL,
                stderr=_sp2.PIPE,
            )

            tables_done = 0
            with open(raw_path, "rb") as f:
                for line in f:
                    proc.stdin.write(line)
                    try:
                        text = line.decode("utf-8", "replace")
                        m = _COPY_RE.match(text)
                        if m:
                            tables_done += 1
                            table_name = m.group(1)
                            _set_restore_progress(
                                "restoring",
                                message=f"Restoring: {table_name}",
                                current_table=table_name,
                                tables_done=tables_done,
                            )
                    except Exception:
                        pass

            proc.stdin.close()
            proc.wait(timeout=900)
            stderr_text = proc.stderr.read().decode(errors="replace")[-500:] if proc.stderr else ""
            return proc.returncode, stderr_text

        loop = asyncio.get_event_loop()
        logger.warning(
            "TRACE upload_restore STEP-5 executor submit", elapsed=f"{_time.monotonic() - t0:.1f}s"
        )

        try:
            returncode, stderr_content = await asyncio.wait_for(
                loop.run_in_executor(None, _run_psql_sync),
                timeout=960,
            )
        except (TimeoutError, _sp.TimeoutExpired):
            raw_path.unlink(missing_ok=True)
            _set_restore_progress("error", message="Restore timed out (10 minutes)")
            logger.error(
                "TRACE upload_restore STEP-5 psql TIMEOUT", elapsed=f"{_time.monotonic() - t0:.1f}s"
            )
            return RestoreResult(
                success=False,
                backup_used=upload_name,
                safety_backup=safety_filename,
                error="psql restore timed out (10 minutes)",
            )

        logger.warning(
            "TRACE upload_restore STEP-6 psql finished",
            returncode=returncode,
            stderr_len=len(stderr_content),
            elapsed=f"{_time.monotonic() - t0:.1f}s",
        )

        logger.warning(
            "TRACE upload_restore STEP-6 psql finished",
            returncode=returncode,
            stderr_len=len(stderr_content),
            elapsed=f"{_time.monotonic() - t0:.1f}s",
        )

        raw_path.unlink(missing_ok=True)

        if returncode != 0:
            logger.error(
                "upload_restore_failed",
                error=stderr_content,
                elapsed=f"{_time.monotonic() - t0:.1f}s",
            )
            return RestoreResult(
                success=False,
                backup_used=upload_name,
                safety_backup=safety_filename,
                error=f"psql restore failed: {stderr_content}",
            )

        _set_restore_progress("done", message="Restore complete!")
        logger.warning(
            "TRACE upload_restore STEP-7 success",
            filename=upload_name,
            safety=safety_filename,
            elapsed=f"{_time.monotonic() - t0:.1f}s",
        )

        from apps.nexus_api.notify import notify_action

        await notify_action(
            action="backup.upload_restored",
            subject="🚨 Database Restored from Upload",
            body=f"Restored from uploaded file: {file.filename} (safety backup: {safety_filename})",
            event_type="nexus.backup.upload_restored",
            severity="critical",
            payload={
                "uploaded_file": file.filename,
                "saved_as": upload_name,
                "safety_backup": safety_filename,
            },
        )
        logger.warning(
            "TRACE upload_restore STEP-8 returning response",
            elapsed=f"{_time.monotonic() - t0:.1f}s",
        )
        return RestoreResult(
            success=True,
            backup_used=upload_name,
            safety_backup=safety_filename,
        )

    except TimeoutError:
        raw_path.unlink(missing_ok=True)
        logger.error("TRACE upload_restore TIMEOUT", elapsed=f"{_time.monotonic() - t0:.1f}s")
        return RestoreResult(
            success=False,
            backup_used=upload_name,
            safety_backup=safety_filename,
            error="Restore timed out (10 minutes). The backup file may be too large for this server.",
        )
    except Exception as e:
        raw_path.unlink(missing_ok=True)
        logger.error(
            "TRACE upload_restore EXCEPTION",
            error=str(e),
            error_type=type(e).__name__,
            elapsed=f"{_time.monotonic() - t0:.1f}s",
        )
        return RestoreResult(
            success=False,
            backup_used=upload_name,
            safety_backup=safety_filename,
            error=str(e) or "Unknown error during restore",
        )


@router.get("/config", response_model=BackupConfigOut)
async def get_config(
    current_user: Any = Depends(RequireRole(["admin"])),
):
    """Get backup configuration."""
    cfg = _load_config()
    # Read the .env value (may differ from container env if changed via GUI)
    env_host_dir = _read_env_value("BACKUP_HOST_DIR", "./backups")
    active_host_dir = os.environ.get("BACKUP_HOST_DIR", "./backups")
    return BackupConfigOut(
        backup_dir=cfg.get("backup_dir", str(BACKUP_DIR)),
        backup_host_dir=env_host_dir,
        max_backups=cfg.get("max_backups", 10),
        backup_count=len(_list_backups()),
        default_location=cfg.get("default_location", "default"),
        locations=_list_locations(),
        pending_restart=cfg.get("pending_restart", False) or (env_host_dir != active_host_dir),
    )


@router.put("/config", response_model=BackupConfigOut)
async def update_config(
    body: BackupConfigIn,
    current_user: Any = Depends(RequireRole(["admin"])),
):
    """Update backup configuration."""
    cfg = _load_config()
    if body.max_backups is not None:
        cfg["max_backups"] = max(1, body.max_backups)
    if body.default_location is not None:
        cfg["default_location"] = body.default_location
    _save_config(cfg)

    await _enforce_retention()

    return BackupConfigOut(
        backup_dir=cfg.get("backup_dir", str(BACKUP_DIR)),
        backup_host_dir=os.environ.get("BACKUP_HOST_DIR", "./backups"),
        max_backups=cfg.get("max_backups", 10),
        backup_count=len(_list_backups()),
        default_location=cfg.get("default_location", "default"),
        locations=_list_locations(),
    )


@router.get("/locations")
async def get_locations(
    current_user: Any = Depends(RequireRole(["admin"])),
):
    """List available backup locations (subdirectories)."""
    return {
        "locations": _list_locations(),
        "backup_host_dir": os.environ.get("BACKUP_HOST_DIR", "./backups"),
    }


class BackupDirUpdate(BaseModel):
    backup_host_dir: str


@router.put("/config/backup-dir")
async def update_backup_dir(
    body: BackupDirUpdate,
    current_user: Any = Depends(RequireRole(["admin"])),
):
    """
    Update the BACKUP_HOST_DIR in .env. Requires a container restart to take effect.
    """
    new_dir = body.backup_host_dir.strip()
    if not new_dir:
        raise HTTPException(status_code=400, detail="Backup directory path cannot be empty")

    # Write to .env file
    success = _write_env_value("BACKUP_HOST_DIR", new_dir)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Could not update .env file — it may not be mounted into the container",
        )

    # Also save to config for reference
    cfg = _load_config()
    cfg["pending_backup_host_dir"] = new_dir
    cfg["pending_restart"] = True
    _save_config(cfg)

    logger.info("backup_dir_changed", new_dir=new_dir)

    from apps.nexus_api.notify import notify_action

    await notify_action(
        action="backup.config_changed",
        subject="⚙️ Backup Directory Changed",
        body=f"Backup directory changed to: {new_dir}. Container restart required.",
        event_type="nexus.backup.config_changed",
        payload={"new_dir": new_dir},
    )

    return {
        "success": True,
        "backup_host_dir": new_dir,
        "message": "Saved. Restart the nexus-api container to apply the new backup directory.",
        "pending_restart": True,
    }
