from django.db import transaction

from chatballs.conversations.access import require_conversation_action
from chatballs.conversations.models import Conversation
from chatballs.conversations.realtime import notify_conversation_changed
from chatballs.notifications.models import Notification
from chatballs.tenancy.context import TenantContext


@transaction.atomic
def delete_conversation(*, context: TenantContext, conversation: Conversation) -> None:
    """Удалить диалог насовсем: переписку, вложения, звонки и оклики о нём.

    Раньше «удалить» означало архив: диалог пропадал из списков, но продолжал
    жить — в него приходили сообщения из канала, он поднимал уведомления и
    возвращался клиенту в виджете как ни в чём не бывало. Решение владельца
    2026-09-14: удалён — значит удалён. Права на это есть только у владельца и
    администратора (проверяет представление).

    Файлы удаляются явно: `FileField` при удалении строки оставляет их на
    диске, а «удалён» не должно означать «лежит в media».
    """
    require_conversation_action(context, conversation, "settings.manage")
    conversation_id = conversation.id
    organization_id = conversation.organization_id
    for message in conversation.messages.exclude(audio="", attachment=""):
        if message.audio:
            message.audio.delete(save=False)
        if message.attachment:
            message.attachment.delete(save=False)
    # Оклик ведёт в диалог, которого больше нет: и в списке уведомлений, и в
    # мессенджере сотрудника такая строка — тупик.
    Notification.objects.filter(
        organization_id=organization_id,
        source_type="Conversation",
        source_id=str(conversation_id),
    ).delete()
    # Звонки держат диалог внешним ключом PROTECT; история звонка без самого
    # диалога ничего не значит, поэтому уходит вместе с ним.
    from chatballs.calls.models import CallSession

    CallSession.objects.filter(conversation_id=conversation_id).delete()
    conversation.delete()
    # Открытые рабочие места узнают об этом событием: у того, кто держал диалог
    # открытым, он должен закрыться, а не висеть мёртвой карточкой.
    notify_conversation_changed(conversation_id, organization_id=organization_id)
