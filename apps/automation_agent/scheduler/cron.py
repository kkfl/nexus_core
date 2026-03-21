import asyncio
import uuid
from datetime import UTC, datetime

import croniter
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.automation_agent.store.postgres import create_run, get_due_cron_automations

logger = structlog.get_logger(__name__)


async def check_cron_schedules(db: AsyncSession):
    """
    Evaluates all active automations with a cron schedule.
    If the schedule indicates it should have run since the last check, enqueue a run.
    """
    now = datetime.now(UTC)

    try:
        automations = await get_due_cron_automations(db)

        for auto in automations:
            try:
                # Basic check: did this tick past a cron boundary in the last minute?
                # A robust implementation tracks last_evaluated_at per automation.
                # For V1 MVP: We check if it matches the current minute (rounded down).
                # To prevent duplicates in the same minute, we use idempotency key based on minute.
                cron = croniter.croniter(auto.schedule_cron, now)

                # We format idempotency key with current YYYY-MM-DD-HH-MM
                time_key = now.strftime("%Y-%m-%d-%H-%M")
                idempotency_key = f"cron_{auto.id}_{time_key}"

                # Check if it should run at exactly this minute
                # croniter get_prev returns the last scheduled time.
                prev = cron.get_prev(datetime)

                # If the previous scheduled time is within this exact minute
                # AND we don't already have a run for this minute (enforced by DB unique constraint on idempotency_key)
                if (
                    prev.year == now.year
                    and prev.month == now.month
                    and prev.day == now.day
                    and prev.hour == now.hour
                    and prev.minute == now.minute
                ):
                    # Create run
                    correlation_id = str(uuid.uuid4())

                    try:
                        run = await create_run(
                            db=db,
                            tenant_id=auto.tenant_id,
                            env=auto.env,
                            idempotency_key=idempotency_key,
                            correlation_id=correlation_id,
                            automation_id=auto.id,
                        )
                        logger.info(
                            "cron_run_enqueued",
                            automation_id=auto.id,
                            run_id=run.id,
                            idempotency_key=idempotency_key,
                        )

                        # Note: we flush to db within the loop so the DB unique constraint prevents duplicate creation
                        await db.commit()

                        # Telegram notification — only for automations running hourly
                        # or less frequently (skip sub-hourly like PBX screen refresh)
                        try:
                            cron_parts = auto.schedule_cron.split()
                            minute_field = cron_parts[0] if cron_parts else "*"
                            # If minute field is * or */N where N < 60, it's sub-hourly
                            is_sub_hourly = (
                                minute_field == "*"
                                or (minute_field.startswith("*/") and int(minute_field[2:]) < 60)
                            )
                            if not is_sub_hourly:
                                from apps.notifications_agent.client.notifications_client import NotificationsClient
                                import os
                                nc = NotificationsClient(
                                    base_url=os.getenv("NOTIFICATIONS_BASE_URL", "http://notifications-agent:8008"),
                                    service_id="automation-agent",
                                    api_key=os.getenv("NEXUS_NOTIF_AGENT_KEY", "nexus-notif-key-change-me"),
                                )
                                await nc.notify(
                                    tenant_id=auto.tenant_id, env=auto.env, severity="info",
                                    channels=["telegram"],
                                    subject="\u23f0 Scheduled Automation",
                                    body=f"{auto.name} (cron: {auto.schedule_cron})",
                                    idempotency_key=f"auto-cron:{idempotency_key}",
                                )
                        except Exception:
                            pass  # fire-and-forget

                    except Exception as ex:
                        if (
                            "unique constraint" in str(ex).lower()
                            or "duplicate key" in str(ex).lower()
                        ):
                            # Already enqueued this minute by another worker tick
                            await db.rollback()
                        else:
                            logger.error(
                                "cron_run_enqueue_failed", automation_id=auto.id, error=str(ex)
                            )
                            await db.rollback()

            except Exception as e:
                logger.error("cron_evaluation_failed", automation_id=auto.id, error=str(e))

    except Exception as e:
        logger.error("cron_scheduler_failed", error=str(e))


async def scheduler_loop(get_db_session_func, tick_interval_sec: int):
    """
    Background task that loops forever, evaluating schedules.
    """
    logger.info("cron_scheduler_started", tick_interval_sec=tick_interval_sec)

    while True:
        try:
            # We fetch a new DB session for each tick
            async for db in get_db_session_func():
                await check_cron_schedules(db)
        except Exception as e:
            logger.error("cron_scheduler_loop_error", error=str(e))

        await asyncio.sleep(tick_interval_sec)
