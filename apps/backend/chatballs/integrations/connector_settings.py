"""Public Connector settings and their server-owned configuration boundary."""

from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from chatballs.i18n import t

MIRROR_ENABLED = "mirrorExternalOutgoingEnabled"
AI_OUTBOUND_ENABLED = "connectorAiOutboundEnabled"
MIRROR_ENABLED_AT = "mirror_external_outgoing_enabled_at"
CONNECTOR_CLOCK_SKEW = timedelta(seconds=30)

_RUNTIME_KEYS = (
    "callback_url", "command_url", "connectorMediaInboundEnabled",
    "connectorMediaOutboundEnabled", "connectorMediaLifecycleEnabled",
    MIRROR_ENABLED_AT,
)


def normalize_connector_config(config: dict, previous: dict) -> dict:
    service = config.get(
        "connectorService", config.get("connector_service", previous.get("connector_service", "")),
    )
    if not isinstance(service, str) or len(service) > 64 or (
        service and not all(
            char.isascii() and (char.islower() or char.isdigit() or char in "_-") for char in service
        )
    ):
        raise ValidationError({"config": t("settings.connector_service_invalid")})
    result = {key: previous[key] for key in _RUNTIME_KEYS if key in previous}
    if service:
        result["connector_service"] = service
    for key in (MIRROR_ENABLED, AI_OUTBOUND_ENABLED):
        was_enabled = previous.get(key) is True
        enabled = config.get(key, was_enabled)
        if type(enabled) is not bool:
            raise ValidationError({key: t("api.boolean_required")})
        if enabled or key in config:
            result[key] = enabled
    return result


def stamp_mirror_cutover(config: dict, previous: dict) -> None:
    if config.get(MIRROR_ENABLED) is True and previous.get(MIRROR_ENABLED) is not True:
        config[MIRROR_ENABLED_AT] = timezone.now().isoformat()


def mirror_is_current(config: dict, *, occurred_at: datetime, observed_at: datetime | None) -> bool:
    if config.get(MIRROR_ENABLED) is not True or observed_at is None:
        return False
    value = config.get(MIRROR_ENABLED_AT)
    if not isinstance(value, str):
        return False
    try:
        enabled_at = parse_datetime(value)
    except ValueError:
        return False
    if enabled_at is None or timezone.is_naive(enabled_at):
        return False
    safe_start = enabled_at + CONNECTOR_CLOCK_SKEW
    now = timezone.now()
    # Only provider occurrence and first durable observation can date a retry.
    return (
        safe_start < min(occurred_at, observed_at)
        and max(occurred_at, observed_at) <= now + CONNECTOR_CLOCK_SKEW
        and occurred_at <= observed_at + 2 * CONNECTOR_CLOCK_SKEW
    )
