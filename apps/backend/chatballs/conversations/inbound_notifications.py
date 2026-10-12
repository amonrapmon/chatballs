"""Notifications after ordinary inbound persistence."""

from chatballs.conversations.models import ControlMode
from chatballs.conversations.queue import is_waiting
from chatballs.i18n import t
from chatballs.notifications.models import NotificationAudience, NotificationType
from chatballs.notifications.services import notify


def notify_inbound(*, context, conversation, channel, contact, integration,
                   inbound, message_text, is_new):
    if is_new:
        # Диалог, которым занялся агент, — это «новый диалог» и больше ничего.
        # Диалог, отвечать в котором некому, — уже просьба о человеке: событие
        # одно, а смысл для смены разный, и подписки на них тоже разные.
        notify(
            context=context,
            type=(
                NotificationType.OPERATOR_REQUESTED
                if is_waiting(conversation)
                else NotificationType.NEW_DIALOG
            ),
            audience=NotificationAudience.OPERATORS,
            audience_group=conversation.group,
            title=f"Новый диалог · {channel.name}",
            body=f"{contact.name or 'Гость'} · {integration.provider}: {message_text[:80]}",
            title_key="notifications.new_dialog",
            body_key="notifications.new_dialog_body",
            text_params={
                "channel": channel.name,
                "contact": contact.name or t("conversations.guest"),
                "provider": integration.provider,
                "preview": message_text[:80],
            },
            target_id=conversation.id,
            source_type="Conversation",
            source_id=conversation.id,
            dedup_key=f"dialog:{conversation.id}",
        )
    elif conversation.control_mode != ControlMode.AI:
        # Клиент написал в диалог, который ведёт оператор или который в очереди — пуш.
        operator = conversation.assigned_operator
        notify(
            context=context,
            type=NotificationType.DIALOG_NEW_MESSAGE,
            audience=NotificationAudience.USER if operator else NotificationAudience.OPERATORS,
            audience_group=conversation.group,
            recipient_user=operator,
            title=f"Новое сообщение · {contact.name or 'Гость'}",
            body=message_text[:120],
            title_key="notifications.new_message",
            text_params={"contact": contact.name or t("conversations.guest")},
            target_id=conversation.id,
            source_type="Conversation",
            source_id=conversation.id,
            dedup_key=f"msg:{integration.id}:{inbound.external_id}",
        )

