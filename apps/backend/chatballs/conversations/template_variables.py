"""Variable keys and catalog derived from server-side conversation visibility."""

import re

from rest_framework.exceptions import NotFound

from chatballs.conversations.models import Conversation
from chatballs.conversations.selectors import conversation_for_context, visible_conversations_for
from chatballs.i18n import t
from chatballs.identity.policy import require_capability
from chatballs.integrations.models import Integration, IntegrationProvider

LEGACY_VARIABLES = ("client_name", "operator_name", "company")
CONTACT_FIELDS = ("email", "phone", "company", "city", "description")
# Capture unknown and malformed keys too: saving must not silently accept them.
TEMPLATE_TOKEN = re.compile(r"\{\{([^{}]*?)\}\}")


def variable_keys(text):
    return list(dict.fromkeys(match.group(1).strip() for match in TEMPLATE_TOKEN.finditer(text)))


def visible_dialog(context, conversation_id):
    try:
        conversation = conversation_for_context(context=context, conversation_id=conversation_id)
        if not require_capability(context.membership, "conversations.view", conversation):
            raise Conversation.DoesNotExist
        return conversation
    except Conversation.DoesNotExist:
        raise NotFound(t("conversations.not_found")) from None


def field_key(integration_id, key):
    # Values are scoped to a connection; identical field keys never collide.
    return f"contact.fields.{integration_id}.{key}"


def field_definitions(context, conversation=None):
    if conversation is None:
        connection_ids = visible_conversations_for(context).order_by().values("connection_id")
    else:
        connection_ids = [conversation.connection_id]
    connections = Integration.objects.filter(
        organization_id=context.organization_id, pk__in=connection_ids,
        provider=IntegrationProvider.WEB,
    ).only("id", "name", "config").order_by("id")
    return {
        field_key(connection.pk, definition["key"]): (connection, definition)
        for connection in connections
        for definition in sorted(connection.config.get("fields", []), key=lambda item: item.get("order", 0))
    }


def allowed_keys(context):
    return {*LEGACY_VARIABLES, *(f"contact.{field}" for field in CONTACT_FIELDS), *field_definitions(context)}


def variable_catalog(context, conversation_id=None):
    conversation = visible_dialog(context, conversation_id) if conversation_id is not None else None
    items = [
        {"key": key, "token": "{{" + key + "}}", "label": t(f"conversations.variable_{key}"), "type": "string"}
        for key in LEGACY_VARIABLES
    ]
    items.extend({
        "key": f"contact.{field}", "token": "{{contact." + field + "}}",
        "label": t(f"conversations.variable_contact_{field}"), "type": "string",
    } for field in CONTACT_FIELDS)
    items.extend({
        "key": key, "token": "{{" + key + "}}", "label": definition["label"],
        "type": definition["type"], "connectionId": connection.pk, "connectionName": connection.name,
    } for key, (connection, definition) in field_definitions(context, conversation).items())
    return items
