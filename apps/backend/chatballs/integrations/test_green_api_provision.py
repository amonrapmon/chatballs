"""Control-plane checks run without real Green API credentials or network."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from rest_framework.views import APIView

from chatballs.api_connector.outbound import validate_command_url
from chatballs.integrations.green_api_provision import (
    GreenApiProvisionView,
    _api_origin,
    _env_config,
)
from chatballs.tenancy.middleware import TenantContextMiddleware


@pytest.mark.parametrize("value", [
    "http://api.green-api.com",
    "https://127.0.0.1",
    "https://localhost",
    "https://attacker.example",
    "https://user:secret@api.green-api.com",
    "https://api.green-api.com/waInstance1",
    "https://api.green-api.com/?token=secret",
])
def test_rejects_untrusted_green_api_urls(value):
    with pytest.raises(ValueError):
        _api_origin(value)


def test_accepts_green_api_hosts_without_exposing_credentials():
    assert _api_origin("https://7103.api.green-api.com/") == "https://7103.api.green-api.com/"
    assert _api_origin("https://7103.media.green-api.com") == "https://7103.media.green-api.com/"


def test_namespaced_command_endpoint_for_isolated_lab():
    url = "https://adapter.example.test/gen209/tg/v1/commands"
    assert validate_command_url(url) == url
    with pytest.raises(ValidationError):
        validate_command_url("https://adapter.example.test/gen209/tg/v1/provision")


def test_backend_adapter_configuration_requires_separate_secret(monkeypatch):
    monkeypatch.setenv("CHATBALLS_GREEN_TG_PROVISION_URL", "http://gen209-tg-gateway:3000/v1/provision")
    monkeypatch.setenv("CHATBALLS_GREEN_TG_COMMAND_URL", "https://adapter.example.test/gen209/tg/v1/commands")
    monkeypatch.setenv("CHATBALLS_CONNECTOR_PUBLIC_BASE_URL", "https://chat.example.test")
    monkeypatch.setenv("CHATBALLS_GREEN_TG_PROVISION_TOKEN", "short")
    with pytest.raises(ValueError):
        _env_config("green_api_telegram")
    monkeypatch.setenv("CHATBALLS_GREEN_TG_PROVISION_TOKEN", "test." + "x" * 48)
    config = _env_config("green_api_telegram")
    assert config["privateUrl"] == "http://gen209-tg-gateway:3000/v1/provision"
    assert config["commandUrl"].endswith("/gen209/tg/v1/commands")



def test_provision_route_exempts_the_outer_request_transaction():
    # The middleware must finish its membership-scoped transaction before
    # processing the POST. Otherwise the token rotation remains uncommitted
    # while the adapter calls back to /state/ to authorize the same token.
    request = SimpleNamespace(path_info=(
        "/api/v1/organizations/c914ff87-2b2c-4f66-8547-c44d1eba5917/"
        "integrations/4/green-api/"
    ))
    assert TenantContextMiddleware._view_manages_own_transaction(request)


def test_provision_capability_check_remains_tenant_scoped(monkeypatch):
    context = object()
    seen = []

    @contextmanager
    def scoped(context_or_id):
        assert context_or_id is context
        seen.append("begin")
        try:
            yield
        finally:
            seen.append("end")

    monkeypatch.setattr(
        "chatballs.integrations.green_api_provision.tenant_atomic", scoped
    )
    with patch.object(APIView, "check_permissions", autospec=True) as parent:
        parent.side_effect = lambda self, request: seen.append("permissions")
        GreenApiProvisionView().check_permissions(
            SimpleNamespace(tenant_context=context)
        )
    assert seen == ["begin", "permissions", "end"]
