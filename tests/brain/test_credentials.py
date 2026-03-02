"""
Tests for Nexus Brain credential controller.

Tests the core credential orchestration logic:
  - Vault alias conventions
  - Password resolution (vault_ref vs inline)
  - Credential store-or-rotate logic
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.nexus_api.brain.credentials import (
    EmailCredentialRequest,
    PbxCredentialRequest,
    _email_vault_alias,
    _pbx_vault_alias,
    provision_pbx_credential,
    store_credential_in_vault,
)


# ---------------------------------------------------------------------------
# Vault alias conventions
# ---------------------------------------------------------------------------


class TestVaultAliasConventions:
    def test_email_alias_format(self):
        alias = _email_vault_alias("user@gsmcall.com")
        assert alias == "email.mailbox.user_at_gsmcall_com.password"

    def test_email_alias_dots_replaced(self):
        alias = _email_vault_alias("admin.test@example.org")
        assert "." not in alias.split("email.mailbox.")[1].split(".password")[0].replace("_", "")
        assert "admin_test_at_example_org" in alias

    def test_pbx_alias_format(self):
        alias = _pbx_vault_alias("Office PBX")
        assert alias == "pbx.ami.office_pbx.secret"

    def test_pbx_alias_lowercase(self):
        alias = _pbx_vault_alias("My-PBX-Server")
        assert alias == "pbx.ami.my-pbx-server.secret"


# ---------------------------------------------------------------------------
# store_credential_in_vault
# ---------------------------------------------------------------------------


class TestStoreCredentialInVault:
    @pytest.mark.asyncio
    async def test_creates_new_secret_when_alias_not_found(self):
        with patch("apps.nexus_api.brain.credentials._vault_request", new_callable=AsyncMock) as mock_req:
            # First call: list secrets returns empty
            mock_req.side_effect = [
                [],  # GET /v1/secrets
                {"id": "new-id", "alias": "test.alias"},  # POST /v1/secrets
            ]

            result = await store_credential_in_vault(
                alias="test.alias", value="secret-value", description="Test"
            )

            assert mock_req.call_count == 2
            # Second call should be POST to create
            second_call = mock_req.call_args_list[1]
            assert second_call[0][0] == "POST"
            assert second_call[0][1] == "/v1/secrets"
            assert second_call[1]["json_data"]["alias"] == "test.alias"
            assert second_call[1]["json_data"]["value"] == "secret-value"

    @pytest.mark.asyncio
    async def test_rotates_when_alias_exists(self):
        with patch("apps.nexus_api.brain.credentials._vault_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [
                [{"id": "existing-id", "alias": "test.alias"}],  # GET /v1/secrets
                {"id": "existing-id", "rotated_at": "2026-01-01T00:00:00Z"},  # POST /rotate
            ]

            result = await store_credential_in_vault(
                alias="test.alias", value="new-secret-value"
            )

            assert mock_req.call_count == 2
            second_call = mock_req.call_args_list[1]
            assert second_call[0][0] == "POST"
            assert "/rotate" in second_call[0][1]
            assert second_call[1]["json_data"]["new_value"] == "new-secret-value"


# ---------------------------------------------------------------------------
# provision_pbx_credential
# ---------------------------------------------------------------------------


class TestProvisionPbxCredential:
    @pytest.mark.asyncio
    async def test_provision_stores_and_returns_alias(self):
        with patch("apps.nexus_api.brain.credentials.store_credential_in_vault", new_callable=AsyncMock) as mock_store:
            mock_store.return_value = {"id": "new-id", "alias": "pbx.ami.test_pbx.secret"}

            req = PbxCredentialRequest(target_name="test_pbx", ami_secret="my-ami-secret")
            result = await provision_pbx_credential(req)

            assert result.ok is True
            assert result.vault_alias == "pbx.ami.test_pbx.secret"
            mock_store.assert_awaited_once()
            call_kwargs = mock_store.call_args[1]
            assert call_kwargs["alias"] == "pbx.ami.test_pbx.secret"
            assert call_kwargs["value"] == "my-ami-secret"

    @pytest.mark.asyncio
    async def test_provision_returns_error_on_failure(self):
        with patch("apps.nexus_api.brain.credentials.store_credential_in_vault", new_callable=AsyncMock) as mock_store:
            mock_store.side_effect = RuntimeError("Vault connection failed")

            req = PbxCredentialRequest(target_name="bad_pbx", ami_secret="secret")
            result = await provision_pbx_credential(req)

            assert result.ok is False
            assert "Vault connection failed" in (result.error or "")


# ---------------------------------------------------------------------------
# EmailCredentialRequest validation
# ---------------------------------------------------------------------------


class TestEmailCredentialRequestValidation:
    def test_valid_create_action(self):
        req = EmailCredentialRequest(email="user@test.com", password="12345678", action="create")
        assert req.action == "create"

    def test_valid_reset_action(self):
        req = EmailCredentialRequest(email="user@test.com", password="12345678", action="reset_password")
        assert req.action == "reset_password"

    def test_password_min_length(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            EmailCredentialRequest(email="user@test.com", password="short", action="create")

    def test_invalid_action_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            EmailCredentialRequest(email="user@test.com", password="12345678", action="delete")
