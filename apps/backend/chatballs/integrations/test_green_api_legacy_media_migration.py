"""Safety checks for one-time legacy MAX lifecycle configuration repair."""
from importlib import import_module

import pytest

repaired_config = import_module(
    "chatballs.integrations.migrations.0039_backfill_legacy_max_media_lifecycle"
).repaired_config


def test_repairs_legacy_max_only_and_preserves_other_config():
    before = {
        "connector_service": "green_api_max",
        "connectorMediaInboundEnabled": True,
        "connectorMediaOutboundEnabled": True,
        "mirrorExternalOutgoingEnabled": True,
        "connectorAiOutboundEnabled": False,
        "callback_url": "https://example.test/callbacks/opaque",
    }
    after = repaired_config(before)

    assert after == {**before, "connectorMediaLifecycleEnabled": True}
    assert before.get("connectorMediaLifecycleEnabled") is None


@pytest.mark.parametrize("config", [
    {"connector_service": "green_api_max", "connectorMediaInboundEnabled": False},
    {"connector_service": "green_api_max", "connectorMediaInboundEnabled": None},
    {"connector_service": "green_api_max", "connectorMediaInboundEnabled": True,
     "connectorMediaLifecycleEnabled": False},
    {"connector_service": "green_api_max", "connectorMediaInboundEnabled": True,
     "connectorMediaLifecycleEnabled": True},
    {"connector_service": "green_api_telegram", "connectorMediaInboundEnabled": True},
    {"connector_service": "custom_service", "connectorMediaInboundEnabled": True},
    {},
    None,
])
def test_skips_non_legacy_or_explicit_configuration(config):
    assert repaired_config(config) is None


def test_repairs_null_and_is_idempotent():
    legacy = {
        "connector_service": "green_api_max",
        "connectorMediaInboundEnabled": True,
        "connectorMediaLifecycleEnabled": None,
    }
    fixed = repaired_config(legacy)
    assert fixed["connectorMediaLifecycleEnabled"] is True
    assert repaired_config(fixed) is None
