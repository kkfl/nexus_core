"""monitoring_task_routes

Revision ID: 009_monitoring_task_routes
Revises: 008_monitoring_agent
Create Date: 2026-02-21 04:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '009_monitoring_task_routes'
down_revision = '008_monitoring_agent'
branch_labels = None
depends_on = None

def upgrade() -> None:
    connection = op.get_bind()
    
    routes = [
        {"task_type": "monitoring.ingest.nagios.statusjson", "capabilities": '["monitoring.ingest.nagios.statusjson"]'},
        {"task_type": "monitoring.ingest.nagios.ndjson", "capabilities": '["monitoring.ingest.nagios.ndjson"]'},
        {"task_type": "monitoring.snapshot", "capabilities": '["monitoring.snapshot"]'},
        {"task_type": "monitoring.alert_to_task", "capabilities": '["monitoring.alert_to_task"]'},
        {"task_type": "triage.alert", "capabilities": '["triage.alert"]'}
    ]
    
    for r in routes:
        connection.execute(
            sa.text(f"INSERT INTO abstract_task_routes (task_type, required_capabilities) VALUES ('{r['task_type']}', '{r['capabilities']}') ON CONFLICT (task_type) DO NOTHING;")
        )

def downgrade() -> None:
    pass
