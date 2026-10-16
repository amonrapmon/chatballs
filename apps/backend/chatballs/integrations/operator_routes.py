"""Independent connections reuse Channel; existing shared routes stay intact."""

from uuid import uuid4

from django.core.exceptions import ValidationError

from chatballs.channels.models import Channel
from chatballs.channels.services import _group_for_channel
from chatballs.i18n import t
from chatballs.integrations.models import PROVIDER_KIND, IntegrationKind

UNSET_GROUP = object()


def new_operator_route(context, data):
    if (data.channel_id is not None or PROVIDER_KIND[data.provider] != IntegrationKind.MESSENGER
            or data.config.get("purpose") == "notifications"):
        return None
    group_id = None if data.group_id is UNSET_GROUP else data.group_id
    _validate_group_id(group_id)
    group = _group_for_channel(context=context, group_id=group_id)
    return Channel.objects.create(
        organization_id=context.organization_id, name=data.name.strip(),
        code=f"connection-{uuid4().hex[:24]}", group=group,
    )


def update_operator_group(context, integration, group_id):
    if group_id is UNSET_GROUP:
        return
    _validate_group_id(group_id)
    channel = integration.channel
    if channel is None:
        raise ValidationError({"groupId": t("channels.not_found")})
    group = _group_for_channel(context=context, group_id=group_id)
    # Shared route edits require the existing agent/route form: never present
    # this as an independent property of one connection.
    if channel.connections.exclude(pk=integration.pk).exists() and channel.group_id != (group.pk if group else None):
        raise ValidationError({"groupId": t("settings.connection_group_shared")})
    channel.group = group
    channel.save(update_fields=["group"])


def _validate_group_id(group_id):
    if group_id is not None and (isinstance(group_id, bool) or not isinstance(group_id, int)):
        raise ValidationError({"groupId": t("ai.group_id_integer_or_null")})
