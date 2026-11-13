"""Control-plane checks run without real Green API credentials or network."""
import pytest
from django.core.exceptions import ValidationError

from chatballs.api_connector.outbound import validate_command_url
from chatballs.integrations.green_api_provision import _api_origin, _env_config


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
