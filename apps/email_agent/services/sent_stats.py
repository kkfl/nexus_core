"""
Sent-mail stats service — batch collection via SSH + DB cache.

Mirrors the mailbox_stats.py pattern:
1) SSH call to /opt/nexus-mail-admin/batch_sent_stats
2) Upsert into Postgres sent_stat_snapshots table
3) Serve from cache with configurable TTL
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

# ── In-memory cache ──────────────────────────────────────────────────────────
_sent_cache: list[dict] | None = None
_sent_cache_ts: float = 0
_refresh_lock = asyncio.Lock()
_refreshing = False


async def _ensure_table() -> None:
    """Auto-create the sent stats table if it doesn't exist."""
    async with async_session() as db:
        await db.execute(
            text("""
                CREATE TABLE IF NOT EXISTS sent_stat_snapshots (
                    sender          VARCHAR(512) PRIMARY KEY,
                    sent_total      INTEGER DEFAULT 0,
                    delivered       INTEGER DEFAULT 0,
                    bounced         INTEGER DEFAULT 0,
                    deferred        INTEGER DEFAULT 0,
                    delivery_rate   REAL DEFAULT 0.0,
                    last_sent_at    VARCHAR(256),
                    period          VARCHAR(32) DEFAULT '24h',
                    collected_at    TIMESTAMPTZ
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


async def refresh_sent_stats(hours_back: int = 24) -> tuple[list[dict], str | None]:
    """
    Fetch sent stats for ALL senders in one SSH call, upsert into Postgres.
    Returns (stats_list, error_message).
    """
    global _sent_cache, _sent_cache_ts, _refreshing

    _refreshing = True
    try:
        await _maybe_ensure_table()

        result = await run_bridge_command("batch_sent_stats", args=[str(hours_back)], timeout=60)

        if not isinstance(result, list):
            err_msg = str(result)[:500]
            logger.error(
                "sent_stats_bad_response",
                result_type=type(result).__name__,
                detail=err_msg,
            )
            return [], f"Bridge returned {type(result).__name__}: {err_msg}"

        logger.info("sent_stats_fetched", count=len(result))

        # Upsert into Postgres
        async with async_session() as db:
            for row in result:
                sender = row.get("sender", "")
                if not sender:
                    continue
                await db.execute(
                    text("""
                        INSERT INTO sent_stat_snapshots
                            (sender, sent_total, delivered, bounced, deferred,
                             delivery_rate, last_sent_at, period, collected_at)
                        VALUES
                            (:sender, :sent_total, :delivered, :bounced, :deferred,
                             :delivery_rate, :last_sent_at, :period, :collected_at)
                        ON CONFLICT (sender) DO UPDATE SET
                            sent_total = EXCLUDED.sent_total,
                            delivered = EXCLUDED.delivered,
                            bounced = EXCLUDED.bounced,
                            deferred = EXCLUDED.deferred,
                            delivery_rate = EXCLUDED.delivery_rate,
                            last_sent_at = EXCLUDED.last_sent_at,
                            period = EXCLUDED.period,
                            collected_at = EXCLUDED.collected_at
                    """),
                    {
                        "sender": sender,
                        "sent_total": int(row.get("sent_total", 0)),
                        "delivered": int(row.get("delivered", 0)),
                        "bounced": int(row.get("bounced", 0)),
                        "deferred": int(row.get("deferred", 0)),
                        "delivery_rate": float(row.get("delivery_rate", 0.0)),
                        "last_sent_at": row.get("last_sent_at"),
                        "period": row.get("period", "24h"),
                        "collected_at": datetime.fromisoformat(
                            row.get("collected_at", datetime.now(UTC).isoformat())
                        ),
                    },
                )
            await db.commit()

        _sent_cache = result
        _sent_cache_ts = time.time()

        return result, None
    except Exception as e:
        logger.error("sent_stats_refresh_error", error=str(e)[:200])
        return [], f"Exception: {e!s}"
    finally:
        _refreshing = False


# ── Read from cache ──────────────────────────────────────────────────────────


async def get_sent_stats_cached() -> dict:
    """
    Return cached sent stats.
    If cache is stale, triggers background refresh and returns stale data.
    Returns: {stats: [...], collected_at: ..., stale: bool, refreshing: bool}
    """
    global _sent_cache, _sent_cache_ts

    await _maybe_ensure_table()

    ttl = config.stats_cache_ttl_seconds
    now = time.time()
    is_stale = (now - _sent_cache_ts) > ttl

    # If in-memory cache is empty, try loading from DB
    if _sent_cache is None:
        async with async_session() as db:
            rows = await db.execute(
                text("SELECT * FROM sent_stat_snapshots ORDER BY sent_total DESC")
            )
            db_rows = rows.mappings().all()
            if db_rows:
                _sent_cache = [dict(r) for r in db_rows]
                for r in _sent_cache:
                    if isinstance(r.get("collected_at"), datetime):
                        r["collected_at"] = r["collected_at"].isoformat()
                _sent_cache_ts = now
                is_stale = False

    # If still empty or stale, trigger background refresh
    if (_sent_cache is None or is_stale) and not _refreshing:
        asyncio.create_task(_background_refresh())

    collected_at = None
    if _sent_cache and len(_sent_cache) > 0:
        collected_at = _sent_cache[0].get("collected_at")

    # Compute totals
    total_sent = sum(s.get("sent_total", 0) for s in (_sent_cache or []))
    total_delivered = sum(s.get("delivered", 0) for s in (_sent_cache or []))
    total_bounced = sum(s.get("bounced", 0) for s in (_sent_cache or []))
    total_deferred = sum(s.get("deferred", 0) for s in (_sent_cache or []))

    return {
        "stats": _sent_cache or [],
        "collected_at": collected_at,
        "stale": is_stale,
        "refreshing": _refreshing,
        "count": len(_sent_cache or []),
        "totals": {
            "sent": total_sent,
            "delivered": total_delivered,
            "bounced": total_bounced,
            "deferred": total_deferred,
            "delivery_rate": round(total_delivered / total_sent * 100, 1)
            if total_sent > 0
            else 0.0,
        },
    }


async def get_sender_stats(email: str) -> dict:
    """Get sent stats for a single sender from cache."""
    cached = await get_sent_stats_cached()
    for s in cached.get("stats", []):
        if s.get("sender") == email:
            return s
    return {
        "sender": email,
        "sent_total": 0,
        "delivered": 0,
        "bounced": 0,
        "deferred": 0,
        "delivery_rate": 0.0,
        "last_sent_at": None,
        "period": "24h",
    }


async def _background_refresh() -> None:
    """Non-blocking background refresh."""
    async with _refresh_lock:
        if _refreshing:
            return
        logger.info("background_sent_stats_refresh_started")
        await refresh_sent_stats()
        logger.info("background_sent_stats_refresh_done")


# ── Per-mailbox sent detail ──────────────────────────────────────────────────


async def get_sent_detail(email: str, limit: int = 50) -> dict:
    """
    Fetch recent sent messages for a specific sender via SSH.
    Not cached — always hits the mail server.
    """
    try:
        result = await run_bridge_command("sent_detail", args=[email, str(limit)], timeout=30)

        if not isinstance(result, list):
            err_msg = str(result)[:500]
            return {"ok": False, "messages": [], "error": err_msg}

        return {
            "ok": True,
            "sender": email,
            "messages": result,
            "count": len(result),
        }
    except Exception as e:
        logger.error("sent_detail_error", sender=email, error=str(e)[:200])
        return {"ok": False, "messages": [], "error": str(e)[:200]}
