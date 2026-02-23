import os
import subprocess

import pytest

# Pytest script to ensure Alembic migrations are clean and reversible (or at least strictly ordered).


@pytest.mark.skipif(
    os.environ.get("RUN_MIGRATION_TESTS", "false").lower() != "true", reason="Requires isolated DB"
)
def test_alembic_upgrade_downgrade():
    """
    Ensures that Alembic can cleanly upgrade to head.
    (Downgrade testing is trickier in Postgres if tables are dropped with constraints,
    so we at least ensure 'upgrade head' on a blank DB succeeds).
    """

    # Run upgrade head
    result = subprocess.run(["alembic", "upgrade", "head"], capture_output=True, text=True)

    assert result.returncode == 0, f"Alembic upgrade failed:\n{result.stderr}\n{result.stdout}"

    # Run a downgrade -1 to ensure the latest migration provides a safe downgrade path
    result_down = subprocess.run(["alembic", "downgrade", "-1"], capture_output=True, text=True)

    assert result_down.returncode == 0, (
        f"Alembic downgrade -1 failed:\n{result_down.stderr}\n{result_down.stdout}"
    )

    # Re-upgrade to leave DB in clean state for next tests
    subprocess.run(["alembic", "upgrade", "head"])
