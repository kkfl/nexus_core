"""
018_agent_registry_tables — agents, deployments, capabilities, audit_events.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "018_agent_registry_tables"
down_revision = "017_notifications_tables"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "registry_agents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("description", sa.Text),
        sa.Column("owner", sa.String(128)),
        sa.Column("tags", ARRAY(sa.String)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True))
    )
    op.create_index("ix_reg_agents_name", "registry_agents", ["name"])

    op.create_table(
        "registry_deployments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("registry_agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(128)),
        sa.Column("env", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(256), nullable=False),
        sa.Column("public_url", sa.String(256)),
        sa.Column("version", sa.String(64)),
        sa.Column("build_sha", sa.String(64)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("health_endpoint", sa.String(256)),
        sa.Column("ready_endpoint", sa.String(256)),
        sa.Column("capabilities_endpoint", sa.String(256)),
        sa.Column("auth_scheme", sa.String(32), nullable=False, server_default="headers"),
        sa.Column("auth_secret_alias", sa.String(128)),
        sa.Column("required_headers", JSONB),
        sa.Column("rate_limits", JSONB),
        sa.Column("timeouts", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True))
    )
    op.create_index("ix_reg_deps_agent", "registry_deployments", ["agent_id"])
    op.create_index("ix_reg_deps_tenant_env", "registry_deployments", ["tenant_id", "env"])

    op.create_table(
        "registry_capabilities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("registry_agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("input_schema", JSONB),
        sa.Column("output_schema", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("agent_id", "name", "version", name="uq_reg_cap")
    )
    op.create_index("ix_reg_caps_agent", "registry_capabilities", ["agent_id"])

    op.create_table(
        "registry_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("service_id", sa.String(128), nullable=False),
        sa.Column("tenant_id", sa.String(128)),
        sa.Column("env", sa.String(32)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("detail", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now())
    )
    op.create_index("ix_reg_audit_tenant_env", "registry_audit_events", ["tenant_id", "env"])
    op.create_index("ix_reg_audit_corr", "registry_audit_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_table("registry_audit_events")
    op.drop_table("registry_capabilities")
    op.drop_table("registry_deployments")
    op.drop_table("registry_agents")
