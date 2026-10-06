"""Данные клиента для привязанных параметров HTTP-инструмента (SPEC-0023 R-4).

Имя, e-mail и телефон берутся из контакта диалога любого подключения, свои
поля — только из веб-подключения самого диалога. Модель привязанных параметров
не видит; без обязательного значения инструмент ей не предлагается.
"""

from __future__ import annotations

from chatballs.ai.provider.base import ToolSpec
from chatballs.conversations.models import ContactFieldValue, Conversation
from chatballs.integrations.http_tool import ClientData, bound_arguments, input_schema
from chatballs.integrations.models import Integration, IntegrationProvider


def _web_fields(conversation: Conversation) -> dict[int, dict[str, object]]:
    if not conversation.connection_id:
        return {}
    # Схема читается заново: значение поля, удалённого из неё, не подставляется.
    config = Integration.objects.filter(
        id=conversation.connection_id,
        organization_id=conversation.organization_id,
        provider=IntegrationProvider.WEB,
    ).values_list("config", flat=True).first()
    if config is None:
        return {}
    keys = [
        field["key"]
        for field in config.get("fields", [])
        if isinstance(field, dict) and field.get("key")
    ]
    values = ContactFieldValue.objects.filter(
        organization_id=conversation.organization_id,
        contact_id=conversation.contact_id,
        integration_id=conversation.connection_id,
        key__in=keys,
    ).values_list("key", "value")
    return {conversation.connection_id: dict(values)}


def conversation_client_data(conversation: Conversation | None) -> ClientData:
    """Данные клиента диалога; без контакта привязывать нечего."""
    contact = getattr(conversation, "contact", None)
    if contact is None:
        return ClientData()
    return ClientData(
        name=contact.name,
        email=contact.email,
        phone=contact.phone,
        web_fields=_web_fields(conversation),
    )


def http_tool_spec(server: Integration, client: ClientData) -> ToolSpec | None:
    """HTTP-инструмент, как его видит модель; None — в этом ходе не предлагается."""
    config = server.config
    if bound_arguments(config, client) is None:
        return None
    return ToolSpec(
        name=str(config.get("tool_name", "")),
        description=str(config.get("description", "")),
        parameters=input_schema(config),
    )
