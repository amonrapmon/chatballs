"""First-send authority for a stored Connector AI command."""

from chatballs.ai.execution_version import configuration_version
from chatballs.conversations.models import Conversation, Message, MessageAuthor, MessageKind
from chatballs.identity.operation_modes import lock_organization
from chatballs.integrations.execution.ai_reply import allowed
from chatballs.integrations.models import Integration, IntegrationProvider
from chatballs.native_mirror.publication import claim_locked_ai_publication
from chatballs.tenancy.context import TenantContext


def claim_connector_delivery(context: TenantContext, candidate: Message, payload: dict) -> Integration | None:
    organization = lock_organization(context.organization_id)
    # Settings and authenticated feedback use this same lock before Conversation.
    connection = Integration.objects.select_for_update(of=("self",), no_key=True).filter(
        pk=payload["integration_id"], organization_id=context.organization_id,
        provider=IntegrationProvider.API_CONNECTOR,
    ).first()
    conversation = Conversation.objects.select_for_update(of=("self",)).get(
        pk=candidate.conversation_id, organization_id=context.organization_id,
    )
    message = Message.objects.select_for_update().get(
        pk=candidate.pk, organization_id=context.organization_id, conversation=conversation,
    )
    command = payload["command"]
    if (connection is None or conversation.connection_id != connection.pk
            or command.get("source_id") != f"connection-{connection.pk}"
            or message.author_type != MessageAuthor.AI or message.kind != MessageKind.TEXT
            or message.connector_delivery.get("commandId") != command.get("command_id")
            or command.get("recipient") != {"external_chat_id": conversation.external_chat_id,
                                             "external_user_id": conversation.route_external_user_id}
            or command.get("message") != {"kind": "text", "text": message.text, "media": []}):
        raise RuntimeError("connector_command_binding_changed")
    if message.connector_delivery.get("state") not in {"QUEUED", "SUPPRESSED"}:
        return None  # A concurrent receipt or accepted retry already owns delivery.

    conversation.connection = connection
    route = message.ai_delivery
    agent = getattr(conversation.channel, "ai_agent", None)

    def authorized():
        return (
            connection.config.get("command_url") == payload["command_url"]
            and conversation.archived_at is None
            and route.get("controlVersion") == conversation.ai_control_version
            and agent is not None and route.get("agentId") == agent.pk
            and route.get("agentVersion") == configuration_version(agent)
            and (not route.get("actionRuns") or allowed(context, conversation.pk, route["actionRuns"]))
        )

    if claim_locked_ai_publication(
        organization, conversation, message, authorize=authorized, allow_own_pause=True,
    ):
        return connection
    return None
