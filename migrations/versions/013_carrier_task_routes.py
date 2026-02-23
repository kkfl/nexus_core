"""carrier_task_routes

Revision ID: 013_carrier_task_routes
Revises: 012_carrier_agent
Create Date: 2026-02-21 05:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '013_carrier_task_routes'
down_revision = '012_carrier_agent'
branch_labels = None
depends_on = None

def upgrade() -> None:
    connection = op.get_bind()
    
    routes = [
        {"task_type": "carrier.account.status", "capabilities": '["carrier.account.status"]'},
        {"task_type": "carrier.dids.list", "capabilities": '["carrier.dids.list"]'},
        {"task_type": "carrier.did.lookup", "capabilities": '["carrier.did.lookup"]'},
        {"task_type": "carrier.trunks.list", "capabilities": '["carrier.trunks.list"]'},
        {"task_type": "carrier.messaging.status", "capabilities": '["carrier.messaging.status"]'},
        {"task_type": "carrier.cnam.status", "capabilities": '["carrier.cnam.status"]'},
        {"task_type": "carrier.snapshot.inventory", "capabilities": '["carrier.snapshot.inventory"]'}
    ]
    
    for r in routes:
        connection.execute(
            sa.text(f"INSERT INTO task_routes (task_type, required_capabilities) VALUES ('{r['task_type']}', '{r['capabilities']}') ON CONFLICT (task_type) DO NOTHING;")
        )

def downgrade() -> None:
    pass
