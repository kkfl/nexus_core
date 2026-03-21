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
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from apps.nexus_api.dependencies import RequireRole
from apps.nexus_api.routers.auth import get_current_user

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


class RunBackupRequest(BaseModel):
    subdirectory: str | None = None


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
    """Scan backup directory and subdirectories for .sql.gz files."""
    backups = []
    # Scan root
    for f in sorted(BACKUP_DIR.glob("nexus_backup_*.sql.gz"), reverse=True):
        stat = f.stat()
        name = f.stem.replace(".sql", "")
        date_str = name.replace("nexus_backup_", "")
        backups.append(BackupInfo(
            filename=f.name,
            size_bytes=stat.st_size,
            size_human=_human_size(stat.st_size),
            created_at=date_str,
            tables_included="all (full database)",
            location="default",
        ))
    # Scan subdirectories
    for subdir in sorted(BACKUP_DIR.iterdir()):
        if subdir.is_dir() and not subdir.name.startswith("."):
            for f in sorted(subdir.glob("nexus_backup_*.sql.gz"), reverse=True):
                stat = f.stat()
                name = f.stem.replace(".sql", "")
                date_str = name.replace("nexus_backup_", "")
                backups.append(BackupInfo(
                    filename=f.name,
                    size_bytes=stat.st_size,
                    size_human=_human_size(stat.st_size),
                    created_at=date_str,
                    tables_included="all (full database)",
                    location=subdir.name,
                ))
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
# Core backup helper (used by endpoint + internal safety backup calls)
# ---------------------------------------------------------------------------


async def _create_backup(subdirectory: str | None = None) -> BackupResult:
    """Core backup logic — runs pg_dump and produces a gzipped SQL file."""
    cfg = _load_config()
    subdir = subdirectory or cfg.get("default_location")
    target_dir = _resolve_backup_dir(subdir)
    location_label = subdir if subdir and subdir not in ("default", "/", ".") else "default"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    filename = f"nexus_backup_{timestamp}.sql.gz"
    filepath = target_dir / filename
    raw_path = target_dir / f".tmp_{filename}.sql"

    try:
        env = _pg_env()
        proc = await asyncio.create_subprocess_exec(
            "pg_dump", "--clean", "--if-exists", "--no-owner",
            "-f", str(raw_path),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[:500]
            logger.error("backup_pg_dump_failed", error=err)
            return BackupResult(success=False, error=f"pg_dump failed: {err}")

        with open(raw_path, "rb") as f_in:
            with gzip.open(filepath, "wb", compresslevel=6) as f_out:
                shutil.copyfileobj(f_in, f_out)

        raw_path.unlink(missing_ok=True)

        size = filepath.stat().st_size
        logger.info("backup_created", filename=filename, size=_human_size(size))

        await _enforce_retention()

        from apps.nexus_api.notify import notify_action
        await notify_action(
            action="backup.created",
            subject="\U0001f4be Backup Created",
            body=f"{filename} ({_human_size(size)})",
            event_type="nexus.backup.created",
            payload={"filename": filename, "size": _human_size(size)},
        )

        return BackupResult(
            success=True,
            filename=filename,
            size_human=_human_size(size),
            location=location_label,
        )

    except asyncio.TimeoutError:
        raw_path.unlink(missing_ok=True)
        filepath.unlink(missing_ok=True)
        return BackupResult(success=False, error="Backup timed out (120s)")
    except Exception as e:
        raw_path.unlink(missing_ok=True)
        filepath.unlink(missing_ok=True)
        logger.error("backup_error", error=str(e))
        return BackupResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/run", response_model=BackupResult)
async def run_backup(
    body: RunBackupRequest | None = None,
    current_user: Any = Depends(RequireRole(["admin"])),
):
    """Trigger a new database backup (pg_dump \u2192 gzipped SQL)."""
    subdirectory = (body.subdirectory if body else None)
    return await _create_backup(subdirectory=subdirectory)


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

    from jose import JWTError, jwt as jose_jwt
    from packages.shared.config import settings

    try:
        payload = jose_jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Verify admin role
    from packages.shared.db import get_db_context
    from sqlalchemy.future import select
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
    """
    if body.confirm != "RESTORE":
        raise HTTPException(
            status_code=400,
            detail='You must send {"confirm": "RESTORE"} to proceed.',
        )

    filepath = BACKUP_DIR / filename
    if not filepath.exists() or not filepath.name.startswith("nexus_backup_"):
        raise HTTPException(status_code=404, detail="Backup not found")

    # Step 1: Auto-create safety backup of current state
    safety_result = await _create_backup()
    safety_filename = safety_result.filename if safety_result.success else None

    # Step 2: Decompress and restore
    try:
        raw_path = BACKUP_DIR / f".tmp_restore_{filename}.sql"
        with gzip.open(filepath, "rb") as f_in:
            with open(raw_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        env = _pg_env()
        proc = await asyncio.create_subprocess_exec(
            "psql", "-f", str(raw_path),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        raw_path.unlink(missing_ok=True)

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[:500]
            logger.error("restore_failed", error=err)
            return RestoreResult(
                success=False,
                backup_used=filename,
                safety_backup=safety_filename,
                error=f"psql restore failed: {err}",
            )

        logger.info("restore_success", filename=filename, safety=safety_filename)

        from apps.nexus_api.notify import notify_action
        await notify_action(
            action="backup.restored",
            subject="⚠️ Database Restored",
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
    current_user: Any = Depends(RequireRole(["admin"])),
):
    """
    BREAK-GLASS UPLOAD & RESTORE — disaster recovery.
    Accepts a .sql.gz file upload. Creates a safety backup of the current
    database first, then restores from the uploaded file.
    Requires confirm="UPLOAD_RESTORE" as a form field.
    """
    if confirm != "UPLOAD_RESTORE":
        raise HTTPException(
            status_code=400,
            detail='You must send confirm="UPLOAD_RESTORE" to proceed.',
        )

    # Validate file
    if not file.filename or not file.filename.endswith(".sql.gz"):
        raise HTTPException(
            status_code=400,
            detail="File must be a .sql.gz backup file.",
        )

    # Save uploaded file
    upload_name = f"uploaded_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    upload_path = BACKUP_DIR / upload_name
    try:
        content = await file.read()
        # Validate it's actually gzip
        if content[:2] != b'\x1f\x8b':
            raise HTTPException(
                status_code=400,
                detail="File does not appear to be a valid gzip archive.",
            )
        with open(upload_path, "wb") as f:
            f.write(content)
        logger.info("upload_restore_file_saved", filename=upload_name, size=len(content))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

    # Step 1: Safety backup of current state
    logger.info("upload_restore_safety_backup")
    safety_result = await _create_backup()
    safety_filename = safety_result.filename if safety_result.success else None

    # Step 2: Decompress and restore
    try:
        raw_path = BACKUP_DIR / f".tmp_upload_restore_{upload_name}.sql"
        with gzip.open(upload_path, "rb") as f_in:
            with open(raw_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        env = _pg_env()
        proc = await asyncio.create_subprocess_exec(
            "psql", "-f", str(raw_path),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

        raw_path.unlink(missing_ok=True)

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[:500]
            logger.error("upload_restore_failed", error=err)
            return RestoreResult(
                success=False,
                backup_used=upload_name,
                safety_backup=safety_filename,
                error=f"psql restore failed: {err}",
            )

        logger.info("upload_restore_success", filename=upload_name, safety=safety_filename)

        from apps.nexus_api.notify import notify_action
        await notify_action(
            action="backup.upload_restored",
            subject="🚨 Database Restored from Upload",
            body=f"Restored from uploaded file: {file.filename} (safety backup: {safety_filename})",
            event_type="nexus.backup.upload_restored",
            severity="critical",
            payload={"uploaded_file": file.filename, "saved_as": upload_name, "safety_backup": safety_filename},
        )
        return RestoreResult(
            success=True,
            backup_used=upload_name,
            safety_backup=safety_filename,
        )

    except Exception as e:
        logger.error("upload_restore_error", error=str(e))
        return RestoreResult(
            success=False,
            backup_used=upload_name,
            safety_backup=safety_filename,
            error=str(e),
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
