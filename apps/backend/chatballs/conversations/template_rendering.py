"""Read-only template substitution; neither values nor template text come from the client."""

from chatballs.conversations.models import ContactFieldValue
from chatballs.conversations.serializer_context import _connection_identity, _contact_is_guest
from chatballs.conversations.site_fields import field_display
from chatballs.conversations.template_access import library_object
from chatballs.conversations.template_models import ReplyTemplate
from chatballs.conversations.template_variables import (
    CONTACT_FIELDS,
    TEMPLATE_TOKEN,
    field_definitions,
    field_key,
    visible_dialog,
)
from chatballs.webchat.field_values import validate_field_value


def _field_values(context, conversation):
    definitions = field_definitions(context, conversation)
    values = {}
    rows = ContactFieldValue.objects.filter(
        organization_id=context.organization_id, contact_id=conversation.contact_id,
        integration_id=conversation.connection_id,
    )
    for row in rows:
        key = field_key(row.integration_id, row.key)
        if key not in definitions or row.value is None:
            continue
        definition = definitions[key][1]
        try:
            value = validate_field_value(row.value, definition)
        except ValueError:
            # An option/type may have changed since the last value was received.
            continue
        values[key] = field_display(definition, value).strip()
    return values


def render_template(context, template_id, conversation_id):
    template = library_object(ReplyTemplate, context.membership, template_id)
    conversation = visible_dialog(context, conversation_id)
    contact = conversation.contact
    values = {
        "client_name": "" if _contact_is_guest(contact, _connection_identity(conversation)) else contact.name,
        "operator_name": context.membership.user.full_name,
        "company": context.organization.name,
        **{f"contact.{field}": getattr(contact, field) for field in CONTACT_FIELDS},
        **_field_values(context, conversation),
    }
    unfilled = []

    def substitute(match):
        key = match.group(1).strip()
        value = str(values.get(key, "")).strip()
        if value:
            return value
        if key not in unfilled:
            unfilled.append(key)
        return match.group(0)

    return {"text": TEMPLATE_TOKEN.sub(substitute, template.text), "unfilledKeys": unfilled}
