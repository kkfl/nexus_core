import os

import pytest
from sqlalchemy import select

# These tests run against the live dockerized app or local DB depending on your config.
# They serve as security regression validation of the core Nexus V1 architecture.


@pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION_TESTS", "false").lower() != "true",
    reason="Integration test only",
)
def test_rbac_enforcement():
    """Verify that a read-only role cannot mutate system state."""
    import requests

    base_url = os.environ.get("NEXUS_API_URL", "http://localhost:8000")

    # Needs a real reader login configured in bootstrap
    res = requests.post(
        f"{base_url}/auth/login",
        data={"username": "reader@local.host", "password": "reader_password"},
    )
    if res.status_code == 200:
        token = res.json().get("access_token")

        # Reader trying to create a Persona
        create_res = requests.post(
            f"{base_url}/personas",
            json={"name": "Hacked", "is_active": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_res.status_code == 403, (
            "RBAC regression: Reader is allowed to write Personas!"
        )


def test_api_keys_are_hashed():
    """Validates that API credentials are NOT plaintext in the database."""
    # Assuming direct DB access for this security assertion
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from packages.shared.models import Secret

    db_url = os.environ.get("DATABASE_URL", "postgresql://nexus:nexus@localhost:5432/nexus")
    engine = create_engine(db_url)

    with Session(engine) as session:
        # Check any carrier or mock target secret
        secrets = session.execute(select(Secret)).scalars().all()
        for secret in secrets:
            assert (
                "sk-" not in secret.ciphertext.decode("utf-8")
                if isinstance(secret.ciphertext, bytes)
                else "sk-" not in secret.ciphertext
            ), "Security Regression: Secret appears plaintext!"


def test_entity_events_append_only():
    """Validate that SoR logs are append-only. Postgres trigger should block updates."""
    import sqlalchemy.exc
    from sqlalchemy import create_engine, update
    from sqlalchemy.orm import Session

    from packages.shared.models import EntityEvent

    db_url = os.environ.get("DATABASE_URL", "postgresql://nexus:nexus@localhost:5432/nexus")
    engine = create_engine(db_url)

    with Session(engine) as session:
        event = session.execute(select(EntityEvent)).scalars().first()
        if event:
            with pytest.raises(sqlalchemy.exc.ProgrammingError) as exc:
                # Try to illegally update an audit record
                session.execute(
                    update(EntityEvent).where(EntityEvent.id == event.id).values(action="hacked")
                )
                session.commit()

            assert (
                "append_only" in str(exc.value)
                or "trigger" in str(exc.value).lower()
                or "read-only" in str(exc.value).lower()
            ), "Security Regression: SoR is mutable!"
