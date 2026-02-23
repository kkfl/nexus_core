"""
Policy Engine — default-deny RBAC for vault access.

Evaluation order:
1. Load all active policies sorted by priority descending (higher = first).
2. For each policy, check: service_id match, alias_pattern match,
   tenant_id match (None = any), env match (None = any).
3. First matching policy wins.
4. If no policy matches → DENY.

Glob matching: uses fnmatch for both service_id and alias_pattern fields.
"""

from __future__ import annotations

import fnmatch
import logging
from collections.abc import Sequence

from apps.secrets_agent.models import VaultPolicy

logger = logging.getLogger(__name__)


class AccessDecision:
    __slots__ = ("allowed", "reason", "policy_id")

    def __init__(self, allowed: bool, reason: str, policy_id: str | None = None):
        self.allowed = allowed
        self.reason = reason
        self.policy_id = policy_id

    def __bool__(self) -> bool:
        return self.allowed


class PolicyEngine:
    """
    Evaluate access control policies for vault operations.
    Instantiate once; pass the list of active policies from DB.
    """

    def __init__(self, policies: Sequence[VaultPolicy]) -> None:
        # Sort by priority descending so higher-priority policies are checked first
        self._policies: list[VaultPolicy] = sorted(policies, key=lambda p: -p.priority)

    def check(
        self,
        *,
        service_id: str,
        action: str,
        secret_alias: str,
        tenant_id: str,
        env: str,
    ) -> AccessDecision:
        """
        Returns AccessDecision(allowed=True/False, reason=...).
        Default deny — MUST be an explicit allow.
        """
        for policy in self._policies:
            if not policy.is_active:
                continue

            # service_id: exact or glob
            if not fnmatch.fnmatch(service_id, policy.service_id):
                continue

            # alias_pattern: glob
            if not fnmatch.fnmatch(secret_alias, policy.alias_pattern):
                continue

            # tenant_id: None = any
            if policy.tenant_id is not None and policy.tenant_id != tenant_id:
                continue

            # env: None = any
            if policy.env is not None and policy.env != env:
                continue

            # action check
            if action in policy.actions:
                return AccessDecision(
                    allowed=True,
                    reason=f"Allowed by policy '{policy.name}' (id={policy.id})",
                    policy_id=policy.id,
                )
            else:
                # Policy matched on identity/alias but action not in allowed list
                return AccessDecision(
                    allowed=False,
                    reason=f"Policy '{policy.name}' matched but action '{action}' not in allowed list {policy.actions}",
                    policy_id=policy.id,
                )

        return AccessDecision(
            allowed=False,
            reason=f"No policy grants service '{service_id}' action '{action}' on alias '{secret_alias}' "
            f"(tenant={tenant_id}, env={env}). Default deny.",
        )
