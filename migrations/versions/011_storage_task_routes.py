"""storage_task_routes

Revision ID: 011_storage_task_routes
Revises: 010_storage_agent
Create Date: 2026-02-21 04:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '011_storage_task_routes'
down_revision = '010_storage_agent'
branch_labels = None
depends_on = None

def upgrade() -> None:
    connection = op.get_bind()
    
    routes = [
        {"task_type": "storage.list", "capabilities": '["storage.list"]'},
        {"task_type": "storage.head", "capabilities": '["storage.head"]'},
        {"task_type": "storage.presign.get", "capabilities": '["storage.presign.get"]'},
        {"task_type": "storage.stats.prefix", "capabilities": '["storage.stats.prefix"]'},
        {"task_type": "storage.copy", "capabilities": '["storage.copy"]'},
        {"task_type": "storage.lifecycle.propose", "capabilities": '["storage.lifecycle.propose"]'},
        {"task_type": "storage.lifecycle.apply", "capabilities": '["storage.lifecycle.apply"]'},
        {"task_type": "storage.delete", "capabilities": '["storage.delete"]'}
    ]
    
    for r in routes:
        connection.execute(
            sa.text(f"INSERT INTO task_routes (task_type, required_capabilities) VALUES ('{r['task_type']}', '{r['capabilities']}') ON CONFLICT (task_type) DO NOTHING;")
        )

def downgrade() -> None:
    pass
