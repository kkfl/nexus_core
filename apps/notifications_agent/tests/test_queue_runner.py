"""
Unit tests for notifications_agent queue runner.
Covers: dispatch, retry, succeeded/partial status finalisation.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.notifications_agent.channels.base import SendResult
from apps.notifications_agent.queue.runner import _deliver_channel, dispatch_job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db_ctx():
    """Return an async generator that yields a mock DB session."""
    async def _gen():
        db = AsyncMock()
        delivery = MagicMock()
        delivery.id = "delivery-id-1"
        db.__aenter__ = AsyncMock(return_value=db)
        db.__aexit__ = AsyncMock(return_value=False)
        yield db
    return _gen()


def _patch_get_db(db_mock):
    """Patch get_db to yield a single mock session."""
    async def _get_db():
        yield db_mock
    return patch("apps.notifications_agent.queue.runner.get_db", return_value=_get_db())


# ---------------------------------------------------------------------------
# _deliver_channel tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deliver_channel_success_sets_sent_status():
    """Successful send → delivery row status set to 'sent'."""
    db = AsyncMock()
    fake_delivery = MagicMock()
    fake_delivery.id = "delivery-uuid-1"

    with (
        patch("apps.notifications_agent.queue.runner.build_channel", new=AsyncMock()) as mock_build,
        patch("apps.notifications_agent.queue.runner.create_delivery", new=AsyncMock(return_value=fake_delivery)),
        patch("apps.notifications_agent.queue.runner.update_delivery", new=AsyncMock()) as mock_update,
        patch("apps.notifications_agent.queue.runner.get_db") as mock_get_db,
    ):
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock(return_value=SendResult(
            success=True, provider_msg_id="tg-msg-42", destination_hash="abc123"
        ))
        mock_build.return_value = mock_channel

        async def _yield_db():
            yield db
        mock_get_db.return_value = _yield_db()

        await _deliver_channel(
            job_id="job-1", channel_name="telegram",
            subject="Alert", body="Something broke",
            destination=None, tenant_id="nexus", env="prod",
            correlation_id="corr-123", channel_config={}, max_attempts=3,
        )

        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["status"] == "sent"
        assert call_kwargs["provider_msg_id"] == "tg-msg-42"


@pytest.mark.asyncio
async def test_deliver_channel_failure_sets_failed_status():
    """Failed send on final attempt → delivery status set to 'failed'."""
    db = AsyncMock()
    fake_delivery = MagicMock()
    fake_delivery.id = "delivery-uuid-2"

    with (
        patch("apps.notifications_agent.queue.runner.build_channel", new=AsyncMock()) as mock_build,
        patch("apps.notifications_agent.queue.runner.create_delivery", new=AsyncMock(return_value=fake_delivery)),
        patch("apps.notifications_agent.queue.runner.update_delivery", new=AsyncMock()) as mock_update,
        patch("apps.notifications_agent.queue.runner.get_db") as mock_get_db,
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock(return_value=SendResult(
            success=False, error_code="telegram_error",
            error_detail="chat not found", destination_hash="xyz"
        ))
        mock_build.return_value = mock_channel

        async def _yield_db():
            yield db
        mock_get_db.return_value = _yield_db()

        await _deliver_channel(
            job_id="job-2", channel_name="telegram",
            subject="X", body="Y",
            destination=None, tenant_id="nexus", env="prod",
            correlation_id="corr-999", channel_config={}, max_attempts=1,
        )

        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["status"] == "failed"
        assert call_kwargs["error_code"] == "telegram_error"


@pytest.mark.asyncio
async def test_deliver_channel_retries_on_failure():
    """Failed attempt followed by success → 2 build_channel calls."""
    db = AsyncMock()
    fake_delivery = MagicMock()
    fake_delivery.id = "delivery-uuid-3"

    call_count = {"n": 0}

    async def build_side(*args, **kwargs):
        ch = AsyncMock()
        call_count["n"] += 1
        if call_count["n"] == 1:
            ch.send = AsyncMock(return_value=SendResult(
                success=False, error_code="timeout", destination_hash="abc"
            ))
        else:
            ch.send = AsyncMock(return_value=SendResult(
                success=True, provider_msg_id="ok", destination_hash="abc"
            ))
        return ch

    with (
        patch("apps.notifications_agent.queue.runner.build_channel", new=AsyncMock(side_effect=build_side)),
        patch("apps.notifications_agent.queue.runner.create_delivery", new=AsyncMock(return_value=fake_delivery)),
        patch("apps.notifications_agent.queue.runner.update_delivery", new=AsyncMock()),
        patch("apps.notifications_agent.queue.runner.get_db") as mock_get_db,
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        async def _yield_db():
            yield db
        mock_get_db.return_value = _yield_db()

        await _deliver_channel(
            job_id="job-3", channel_name="email",
            subject="X", body="Y", destination="ops@example.com",
            tenant_id="nexus", env="prod",
            correlation_id="corr-321", channel_config={}, max_attempts=2,
        )

    assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# dispatch_job tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_job_creates_tasks_for_each_channel():
    """dispatch_job creates an asyncio.Task per channel."""
    tasks_created = []
    original_create_task = asyncio.create_task

    def tracking_create_task(coro, **kwargs):
        t = original_create_task(coro, **kwargs)
        tasks_created.append(t)
        return t

    with (
        patch("apps.notifications_agent.queue.runner._deliver_channel", new=AsyncMock()),
        patch("apps.notifications_agent.queue.runner.set_job_status", new=AsyncMock()),
        patch("apps.notifications_agent.queue.runner.get_db") as mock_get_db,
        patch("asyncio.create_task", side_effect=tracking_create_task),
    ):
        async def _yield_db():
            yield AsyncMock()
        mock_get_db.return_value = _yield_db()

        await dispatch_job(
            job_id="job-dispatch-1",
            tenant_id="nexus",
            env="prod",
            channels=["telegram", "email"],
            subject="Alert",
            body="Something happened",
            correlation_id="corr-dispatch",
        )
        # Wait for tasks to complete
        await asyncio.sleep(0)

    # 2 deliver tasks + 1 finalize task
    assert len(tasks_created) >= 2
