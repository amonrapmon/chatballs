import logging

from django.db.models import Q

from chatballs.conversations import transports
from chatballs.conversations.email_inbound import ingest_email_continuation
from chatballs.conversations.ingest import ingest_inbound
from chatballs.integrations.models import Integration, IntegrationProvider
from chatballs.native_mirror.vk_adapter import VkNativeReply, observe_vk_reply

logger = logging.getLogger(__name__)


def poll_all_messengers(context) -> int:
    """Poll bound messengers and agent-independent mailboxes; return ingested count."""
    # Сервисные боты уведомлений поллятся отдельно (notifications.binding).
    # Фильтр по config — в Python: JSON-lookup в .exclude() отбрасывает и строки
    # без ключа purpose (NULL в SQL), т.е. все клиентские боты.
    integrations = [
        integration
        for integration in Integration.objects.filter(
            organization=context.organization,
            provider__in=transports.SUPPORTED_PROVIDERS,
            is_active=True,
        ).filter(
            Q(channel__isnull=False, channel__is_active=True)
            | Q(provider="EMAIL", kind="MESSENGER"),
        ).exclude(secret="").select_related("channel")
        if integration.config.get("purpose") != "notifications"
        # Демо-подключения из демо-набора: токены ненастоящие, опрашивать нечего.
        and not integration.config.get("demoSeed")
    ]
    total = 0
    for integration in integrations:
        messages, new_marker = transports.poll(integration)
        vk_batch_failed = False
        for inbound in messages:
            try:
                if isinstance(inbound, VkNativeReply):
                    if integration.provider != IntegrationProvider.VK:
                        raise ValueError("VK reply in non-VK poll batch")
                    observe_vk_reply(integration, inbound, context=context)
                elif _ingest_polled(integration, inbound):
                    total += 1
            except Exception:
                logger.exception("Ingest failed for integration %s", integration.id)
                # Unlike legacy transports, VK must redeliver this whole
                # batch. Previously ts advanced even when an item failed.
                if integration.provider == IntegrationProvider.VK:
                    vk_batch_failed = True
        if vk_batch_failed:
            logger.warning("VK poll marker kept after failed batch integration=%s", integration.id)
            continue
        if new_marker and new_marker != integration.poll_marker:
            integration.poll_marker = new_marker
            integration.save(update_fields=["poll_marker", "updated_at"])
    return total


def _ingest_polled(integration, inbound) -> bool:
    if integration.provider == "EMAIL" and (
        not integration.channel_id or not integration.channel.is_active
    ):
        # Канал письма-продолжения берётся из исходного WEB-диалога.
        # Без обычного маршрута новые несвязанные письма не создают обращений.
        return ingest_email_continuation(integration, inbound)
    ingest_inbound(integration, inbound)
    return True
