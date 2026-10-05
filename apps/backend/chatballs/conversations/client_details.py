"""Подробная карточка контакта и связанная история."""

from django.db.models import Q

from chatballs.conversations.client_common import PROVIDER_CODE, _actor_name, _mode
from chatballs.conversations.contact_avatars import contact_avatar_url_in
from chatballs.conversations.models import Contact, ContactMerge, Conversation, LifecycleState
from chatballs.conversations.site_fields import site_fields_payload
from chatballs.i18n import t
from chatballs.identity.audit_catalog import (
    audit_action_label,
    audit_object_label,
    audit_result_label,
)
from chatballs.identity.avatars import user_avatar_url_in
from chatballs.identity.models import AuditEvent


def _dialog_status(conversation: Conversation) -> str:
    return {
        "closed": t("conversations.dialog_status_closed"),
        "operator": t("conversations.dialog_status_operator"),
        "ai": "AI",
        "wait": t("conversations.dialog_status_wait"),
    }[_mode(conversation)]


def client_detail(organization_id: int, contact_id: int) -> dict:
    contact = Contact.objects.get(organization_id=organization_id, id=contact_id)
    conversation_qs = Conversation.objects.filter(
        organization_id=organization_id, contact=contact
    ).select_related("channel", "connection", "group", "assigned_operator", "note_author")
    conversations = list(conversation_qs.order_by("-last_activity_at"))
    if not conversations:
        raise Contact.DoesNotExist

    channels: set[str] = set()
    open_dialogs = 0
    dialogs: list[dict] = []
    for conversation in conversations:
        provider = conversation.connection.provider if conversation.connection_id else None
        if provider in PROVIDER_CODE:
            channels.add(PROVIDER_CODE[provider])
        if conversation.lifecycle == LifecycleState.OPEN:
            open_dialogs += 1
        # Тема диалога — первое сообщение, превью — последнее (кадр K4).
        first = conversation.messages.order_by("created_at").first()
        last = conversation.messages.order_by("-created_at").first()
        title = (first.text.replace("\n", " ")[:80] if first and first.text else conversation.channel.name)
        preview = (last.text.replace("\n", " ")[:120] if last and last.text else "")
        dialogs.append(
            {
                "id": conversation.id,
                "title": title,
                "preview": preview,
                "channelName": conversation.channel.name,
                "agentName": conversation.channel.name,
                "agentId": conversation.channel_id,
                "agentCode": conversation.channel.code,
                "groupName": conversation.group.name if conversation.group_id else "",
                "groupColor": conversation.group.color if conversation.group_id else "",
                "assignee": _actor_name(conversation.assigned_operator),
                "assigneeAvatarUrl": user_avatar_url_in(conversation.assigned_operator, organization_id),
                "note": conversation.note,
                "noteAuthor": _actor_name(conversation.note_author),
                "noteUpdatedAt": conversation.note_updated_at.isoformat() if conversation.note_updated_at else None,
                "provider": provider,
                "mode": _mode(conversation),
                "status": _dialog_status(conversation),
                "active": conversation.lifecycle == LifecycleState.OPEN,
                "lastActivityAt": conversation.last_activity_at.isoformat(),
            }
        )

    identity_qs = contact.identities.select_related("connection")
    identities = [
        {
            "provider": identity.connection.provider,
            "value": (
                identity.external_user_id
                if identity.connection.provider == "EMAIL"
                else identity.display_name or identity.external_user_id
            ),
            "externalUserId": identity.external_user_id,
            "username": identity.username,
            "createdAt": identity.created_at.isoformat(),
            # Подтверждённой считается идентичность, отдавшая телефон (ADR-CHATBALLS-0006).
            "phoneVerifiedAt": identity.phone_verified_at.isoformat() if identity.phone_verified_at else None,
        }
        for identity in identity_qs.order_by("created_at")
    ]

    # Активность из жизненного цикла диалогов (created/closed) — реальные события.
    activity: list[dict] = []
    for conversation in conversations:
        activity.append({"type": "created", "title": t("conversations.activity_started", channel=conversation.channel.name), "at": conversation.created_at.isoformat()})
        if conversation.lifecycle == LifecycleState.CLOSED:
            activity.append({"type": "closed", "title": t("conversations.activity_closed", channel=conversation.channel.name), "at": conversation.last_activity_at.isoformat()})
    activity.sort(key=lambda item: item["at"], reverse=True)

    conversation_ids = [str(conversation.id) for conversation in conversations]
    audit = []
    audit_scope = Q(object_type="Conversation", object_id__in=conversation_ids)
    audit_scope |= Q(object_type="Contact", object_id=str(contact_id))
    audit_qs = (
        AuditEvent.objects.filter(organization_id=organization_id)
        .filter(audit_scope)
        .select_related("actor")
        .order_by("-created_at")[:20]
    )
    for event in audit_qs:
        audit.append(
            {
                "time": event.created_at.isoformat(),
                # Подписи, типы объектов и результаты — из общего каталога
                # журнала действий: коды действий и enum-значения на экран
                # карточки не попадают. Пустая подпись означает «её ещё нет»,
                # тогда показываем код — как в журнале.
                "action": audit_action_label(event.action) or event.action,
                "object": audit_object_label(event.object_type, event.object_id),
                "actor": (event.actor.full_name or event.actor.email) if event.actor_id else t("admin.actor_system"),
                "result": audit_result_label(event.result),
            }
        )

    return {
        "id": contact.id,
        "cid": f"CUS-{contact.id}",
        "name": contact.name or t("conversations.guest"),
        # Признак анонимного посетителя: интерфейс красит его аватар иначе.
        # Раньше он выводился из самой подписи регуляркой по слову «Гость» —
        # на другом языке это перестало бы работать.
        "isGuest": not contact.name,
        "phone": contact.phone,
        "avatarUrl": contact_avatar_url_in(contact, contact.organization_id),
        # Поля карточки из чата (описание, компания, город).
        "description": contact.description,
        "company": contact.company,
        "city": contact.city,
        "email": contact.email or next(
            (
                identity.external_user_id
                for identity in identity_qs
                if identity.connection.provider == "EMAIL"
            ),
            "",
        ),
        "siteFields": site_fields_payload(contact),
        "channels": sorted(channels),
        "openDialogs": open_dialogs,
        "totalDialogs": len(conversations),
        "firstContactAt": contact.created_at.isoformat(),
        "lastActivityAt": conversations[0].last_activity_at.isoformat() if conversations else contact.created_at.isoformat(),
        "dialogs": dialogs,
        "identities": identities,
        "activity": activity[:8],
        "audit": audit,
        "duplicate": _duplicate_candidate(organization_id, contact),
        "merges": _merges(organization_id, contact),
    }


def _merges(organization_id: int, contact: Contact) -> list[dict]:
    """Действующие объединения этого контакта — их можно разъединить."""
    rows = (
        ContactMerge.objects.filter(organization_id=organization_id, target=contact, reverted_at__isnull=True)
        .select_related("source", "actor")
        .order_by("-created_at")
    )
    return [
        {
            "id": row.id,
            "sourceId": row.source_id,
            "sourceName": row.source.name or t("conversations.guest"),
            "sourceCid": f"CUS-{row.source_id}",
            "reason": row.reason,
            "actor": _actor_name(row.actor),
            "at": row.created_at.isoformat(),
            "identities": len(row.moved_identity_ids),
            "conversations": len(row.moved_conversation_ids),
        }
        for row in rows
    ]


def _duplicate_candidate(organization_id: int, contact: Contact) -> dict | None:
    """Другой контакт с тем же телефоном. Автоматически ничего не объединяем
    (ADR-CHATBALLS-0006) — это только предложение владельцу."""
    if not contact.phone:
        return None
    other = (
        Contact.objects.filter(organization_id=organization_id, phone=contact.phone, merged_into__isnull=True)
        .exclude(id=contact.id)
        .prefetch_related("identities__connection", "conversations")
        .first()
    )
    if other is None:
        return None
    identities = list(other.identities.all())
    return {
        "id": other.id,
        "cid": f"CUS-{other.id}",
        "name": other.name or t("conversations.guest"),
        "isGuest": not other.name,
        "avatarUrl": contact_avatar_url_in(other, other.organization_id),
        "dialogs": other.conversations.count(),
        "sources": sorted({identity.connection.provider for identity in identities}),
        "phone": other.phone,
        # Однозначным совпадение считается, только если телефон подтверждён
        # подключением хотя бы у одной стороны (ADR-CHATBALLS-0006).
        "phoneVerified": any(identity.phone_verified_at is not None for identity in identities),
    }
