"""Unit tests for the Policy Engine."""
from apps.secrets_agent.models import VaultPolicy
from apps.secrets_agent.policy.engine import PolicyEngine


def _make_policy(**kwargs) -> VaultPolicy:
    defaults = dict(
        id="test-id",
        name="test-policy",
        service_id="pbx-agent",
        alias_pattern="pbx.*",
        tenant_id=None,
        env=None,
        actions=["read"],
        priority=100,
        is_active=True,
        created_at=__import__("datetime").datetime.utcnow(),
        updated_at=__import__("datetime").datetime.utcnow(),
    )
    defaults.update(kwargs)
    p = VaultPolicy.__new__(VaultPolicy)
    for k, v in defaults.items():
        setattr(p, k, v)
    return p


def test_default_deny_no_policies():
    engine = PolicyEngine([])
    decision = engine.check(
        service_id="pbx-agent", action="read",
        secret_alias="pbx.sip.password", tenant_id="nexus", env="prod",
    )
    assert not decision.allowed
    assert "Default deny" in decision.reason


def test_exact_match_allow():
    policy = _make_policy(service_id="pbx-agent", alias_pattern="pbx.sip.password", actions=["read"])
    engine = PolicyEngine([policy])
    decision = engine.check(
        service_id="pbx-agent", action="read",
        secret_alias="pbx.sip.password", tenant_id="nexus", env="prod",
    )
    assert decision.allowed


def test_glob_service_allow():
    policy = _make_policy(service_id="*", alias_pattern="pbx.*", actions=["read", "list_metadata"])
    engine = PolicyEngine([policy])
    decision = engine.check(
        service_id="dns-agent", action="read",
        secret_alias="pbx.something", tenant_id="nexus", env="prod",
    )
    assert decision.allowed


def test_action_not_in_list_deny():
    policy = _make_policy(service_id="pbx-agent", alias_pattern="pbx.*", actions=["list_metadata"])
    engine = PolicyEngine([policy])
    decision = engine.check(
        service_id="pbx-agent", action="read",
        secret_alias="pbx.sip.password", tenant_id="nexus", env="prod",
    )
    assert not decision.allowed
    assert "list_metadata" in decision.reason


def test_tenant_mismatch_deny():
    policy = _make_policy(service_id="pbx-agent", alias_pattern="*", actions=["read"],
                          tenant_id="tenant-A")
    engine = PolicyEngine([policy])
    decision = engine.check(
        service_id="pbx-agent", action="read",
        secret_alias="any.secret", tenant_id="tenant-B", env="prod",
    )
    assert not decision.allowed


def test_env_mismatch_deny():
    policy = _make_policy(service_id="pbx-agent", alias_pattern="*", actions=["read"], env="prod")
    engine = PolicyEngine([policy])
    decision = engine.check(
        service_id="pbx-agent", action="read",
        secret_alias="any.secret", tenant_id="nexus", env="dev",
    )
    assert not decision.allowed


def test_priority_first_match_wins():
    """Higher-priority policy allowing read wins over lower-priority deny."""
    allow_policy = _make_policy(
        id="allow", name="allow", service_id="pbx-agent", alias_pattern="pbx.*",
        actions=["read"], priority=200,
    )
    deny_policy = _make_policy(
        id="deny", name="deny", service_id="pbx-agent", alias_pattern="pbx.*",
        actions=["list_metadata"], priority=50,
    )
    engine = PolicyEngine([deny_policy, allow_policy])  # intentionally reversed order
    decision = engine.check(
        service_id="pbx-agent", action="read",
        secret_alias="pbx.sip.password", tenant_id="nexus", env="prod",
    )
    assert decision.allowed
    assert decision.policy_id == "allow"
