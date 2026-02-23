"""pbx_task_routes

Revision ID: 007_pbx_task_routes
Revises: 006_pbx_agent
Create Date: 2026-02-21 03:40:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "007_pbx_task_routes"
down_revision = "006_pbx_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use raw SQL to insert default routes
    connection = op.get_bind()

    routes = [
        {"task_type": "pbx.status", "capabilities": '["pbx.status"]'},
        {"task_type": "pbx.channels.active", "capabilities": '["pbx.channels.active"]'},
        {"task_type": "pbx.endpoints.list", "capabilities": '["pbx.endpoints.list"]'},
        {"task_type": "pbx.registrations.list", "capabilities": '["pbx.registrations.list"]'},
        {"task_type": "pbx.trunks.list", "capabilities": '["pbx.trunks.list"]'},
        {"task_type": "pbx.dialplan.contexts", "capabilities": '["pbx.dialplan.contexts"]'},
        {"task_type": "pbx.snapshot.inventory", "capabilities": '["pbx.snapshot.inventory"]'},
    ]

    for r in routes:
        connection.execute(
            sa.text(
                f"INSERT INTO task_routes (task_type, required_capabilities) VALUES ('{r['task_type']}', '{r['capabilities']}') ON CONFLICT (task_type) DO NOTHING;"
            )
        )


def downgrade() -> None:
    pass
