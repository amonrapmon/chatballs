"""Признак «Видит AI» своего поля становится режимом доступа (SPEC-0022 R-11).

``ai_visible: false`` — ``hidden``. ``ai_visible: true`` — ``masked`` для
строки, почты, телефона и ссылки: в них бывает свободный текст и персональные
данные; ``open`` для числа, флага, даты и списка.
"""

from django.db import migrations

MASKED_TYPES = frozenset({"string", "email", "phone", "url"})


def _web_integrations(apps):
    Integration = apps.get_model("integrations", "Integration")
    for integration in Integration.objects.filter(provider="WEB").order_by("id"):
        config = integration.config
        if isinstance(config, dict) and isinstance(config.get("fields"), list):
            yield integration


def _to_access(field: dict) -> dict:
    if not isinstance(field, dict) or "ai_access" in field:
        return field
    converted = {key: value for key, value in field.items() if key != "ai_visible"}
    if field.get("ai_visible") is True:
        converted["ai_access"] = "masked" if field.get("type") in MASKED_TYPES else "open"
    else:
        converted["ai_access"] = "hidden"
    return converted


def _to_visible(field: dict) -> dict:
    if not isinstance(field, dict) or "ai_access" not in field:
        return field
    reverted = {key: value for key, value in field.items() if key != "ai_access"}
    reverted["ai_visible"] = field["ai_access"] != "hidden"
    return reverted


def _rewrite(apps, convert) -> None:
    for integration in _web_integrations(apps):
        fields = [convert(field) for field in integration.config["fields"]]
        if fields != integration.config["fields"]:
            integration.config = {**integration.config, "fields": fields}
            integration.save(update_fields=["config"])


def forward(apps, schema_editor):
    _rewrite(apps, _to_access)


def backward(apps, schema_editor):
    _rewrite(apps, _to_visible)


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0010_integration_runtime_revision"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
