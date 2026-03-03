"""
Mailbox stats service — batch collection via single SSH bridge call.

Replaces the old N-calls-per-mailbox approach with:
1) One SSH call to /opt/nexus-mail-admin/batch_mailbox_stats
2) Upsert results into Postgres mailbox_stat_snapshots table
3) Serve from cache (DB) with configurable TTL
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

import structlog
from sqlalchemy import text

from apps.email_agent.client.ssh_bridge import run_bridge_command
from apps.email_agent.config import config
from apps.email_agent.store.database import async_session

logger = structlog.get_logger(__name__)

# ── In-memory cache for bulk stats ───────────────────────────────────────────
_bulk_cache: dict | None = None
_bulk_cache_ts: float = 0
_refresh_lock = asyncio.Lock()
_refreshing = False


async def _ensure_table() -> None:
    """Auto-create the snapshots table if it doesn't exist."""
    async with async_session() as db:
        await db.execute(
            text("""
                CREATE TABLE IF NOT EXISTS mailbox_stat_snapshots (
                    email       VARCHAR(512) PRIMARY KEY,
                    domain      VARCHAR(256),
                    quota_mb    INTEGER DEFAULT 0,
                    used_mb     INTEGER DEFAULT 0,
                    used_pct    INTEGER DEFAULT 0,
                    free_mb     INTEGER DEFAULT 0,
                    free_pct    INTEGER DEFAULT 0,
                    unread_count INTEGER DEFAULT 0,
                    total_count  INTEGER DEFAULT 0,
                    last_received_at VARCHAR(256),
                    collected_at TIMESTAMPTZ,
                    source      VARCHAR(64) DEFAULT 'doveadm'
                )
            """)
        )
        await db.commit()


_table_ensured = False


async def _maybe_ensure_table() -> None:
    global _table_ensured
    if not _table_ensured:
        await _ensure_table()
        _table_ensured = True


# ── Refresh: single SSH call + DB upsert ─────────────────────────────────────


async def refresh_stats() -> tuple[list[dict], str | None]:
    """
    Fetch stats for ALL mailboxes in one SSH call, upsert into Postgres.
    Returns (stats_list, error_message).
    """
    global _bulk_cache, _bulk_cache_ts, _refreshing

    _refreshing = True
    try:
        await _maybe_ensure_table()

        # Single SSH call to batch script (increased timeout via bridge)
        result = await run_bridge_command("batch_mailbox_stats", timeout=120)

        if not isinstance(result, list):
            err_msg = str(result)[:500]
            logger.error(
                "batch_stats_bad_response", result_type=type(result).__name__, detail=err_msg
            )
            return [], f"Bridge returned {type(result).__name__}: {err_msg}"

        logger.info("batch_stats_fetched", count=len(result))

        # Upsert into Postgres
        async with async_session() as db:
            for row in result:
                email = row.get("email", "")
                if not email:
                    continue
                await db.execute(
                    text("""
                        INSERT INTO mailbox_stat_snapshots
                            (email, domain, quota_mb, used_mb, used_pct, free_mb, free_pct,
                             unread_count, total_count, last_received_at, collected_at, source)
                        VALUES
                            (:email, :domain, :quota_mb, :used_mb, :used_pct, :free_mb, :free_pct,
                             :unread_count, :total_count, :last_received_at, :collected_at, 'doveadm')
                        ON CONFLICT (email) DO UPDATE SET
                            domain = EXCLUDED.domain,
                            quota_mb = EXCLUDED.quota_mb,
                            used_mb = EXCLUDED.used_mb,
                            used_pct = EXCLUDED.used_pct,
                            free_mb = EXCLUDED.free_mb,
                            free_pct = EXCLUDED.free_pct,
                            unread_count = EXCLUDED.unread_count,
                            total_count = EXCLUDED.total_count,
                            last_received_at = EXCLUDED.last_received_at,
                            collected_at = EXCLUDED.collected_at
                    """),
                    {
                        "email": email,
                        "domain": row.get("domain", ""),
                        "quota_mb": int(row.get("quota_mb", 0)),
                        "used_mb": int(float(row.get("used_mb", 0))),
                        "used_pct": int(float(row.get("used_pct", 0))),
                        "free_mb": int(float(row.get("free_mb", 0))),
                        "free_pct": int(float(row.get("free_pct", 0))),
                        "unread_count": int(row.get("unread_count", 0)),
                        "total_count": int(row.get("total_count", 0)),
                        "last_received_at": row.get("last_received_at"),
                        "collected_at": datetime.fromisoformat(
                            row.get("collected_at", datetime.now(UTC).isoformat())
                        ),
                    },
                )
            await db.commit()

        # Update in-memory cache
        _bulk_cache = result
        _bulk_cache_ts = time.time()

        return result, None
    except Exception as e:
        logger.error("batch_stats_refresh_error", error=str(e)[:200])
        return [], f"Exception: {e!s}"
    finally:
        _refreshing = False


# ── Read from cache ──────────────────────────────────────────────────────────


async def get_bulk_stats_cached() -> dict:
    """
    Return cached bulk stats.
    If cache is stale, triggers background refresh and returns stale data.
    Returns: {stats: [...], collected_at: ..., stale: bool, refreshing: bool}
    """
    global _bulk_cache, _bulk_cache_ts

    await _maybe_ensure_table()

    ttl = config.stats_cache_ttl_seconds
    now = time.time()
    is_stale = (now - _bulk_cache_ts) > ttl

    # If in-memory cache is empty, try loading from DB
    if _bulk_cache is None:
        async with async_session() as db:
            rows = await db.execute(text("SELECT * FROM mailbox_stat_snapshots ORDER BY email"))
            db_rows = rows.mappings().all()
            if db_rows:
                _bulk_cache = [dict(r) for r in db_rows]
                # Convert collected_at to string for JSON
                for r in _bulk_cache:
                    if isinstance(r.get("collected_at"), datetime):
                        r["collected_at"] = r["collected_at"].isoformat()
                _bulk_cache_ts = now
                is_stale = False

    # If still empty or stale, trigger background refresh
    if (_bulk_cache is None or is_stale) and not _refreshing:
        asyncio.create_task(_background_refresh())

    collected_at = None
    if _bulk_cache and len(_bulk_cache) > 0:
        collected_at = _bulk_cache[0].get("collected_at")

    return {
        "stats": _bulk_cache or [],
        "collected_at": collected_at,
        "stale": is_stale,
        "refreshing": _refreshing,
        "count": len(_bulk_cache or []),
    }


async def _background_refresh() -> None:
    """Non-blocking background refresh."""
    async with _refresh_lock:
        if _refreshing:
            return
        logger.info("background_stats_refresh_started")
        await refresh_stats()
        logger.info("background_stats_refresh_done")


# ── Legacy single-mailbox (kept for per-mailbox endpoint) ────────────────────


async def get_mailbox_stats(email: str, quota_mb: int = 0) -> dict:
    """Get stats for a single mailbox from cache."""
    cached = await get_bulk_stats_cached()
    for s in cached.get("stats", []):
        if s.get("email") == email:
            return s
    # Fall back to empty
    return {
        "email": email,
        "quota_mb": quota_mb,
        "used_mb": 0,
        "used_pct": 0,
        "free_mb": 0,
        "free_pct": 100,
        "unread_count": 0,
        "total_count": 0,
        "last_received_at": None,
    }
