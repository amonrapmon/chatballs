"""Real clients list (contacts + their conversations).

A "client" is a Contact. Commerce data was removed with the sales domain
(ADR-CHATBALLS-0041) — no orders or revenue here.
"""

from __future__ import annotations

from django.db.models import (
    Count,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce

from chatballs.conversations.client_common import PROVIDER_CODE, _actor_name, _mode
from chatballs.conversations.client_details import client_detail as client_detail
from chatballs.conversations.contact_avatars import contact_avatar_url_in
from chatballs.conversations.models import (
    ConnectionIdentity,
    Contact,
    Conversation,
    LifecycleState,
)
from chatballs.i18n import t

# Провайдер подключения по короткому коду канала из фильтра списка (кадр K1).
PROVIDER_BY_CODE = {code: provider for provider, code in PROVIDER_CODE.items()}


def _client_counts(*, lifecycle: str | None = None) -> Subquery:
    """Число диалогов контакта отдельным подзапросом.

    Через join-агрегат считать нельзя: фильтры списка (агент, канал) идут по
    той же связи и урезали бы счётчик до отфильтрованных строк.
    """
    conversations = (
        Conversation.objects.filter(contact_id=OuterRef("pk"))
        .order_by()
        .values("contact_id")
        .annotate(total=Count("id"))
        .values("total")
    )
    if lifecycle:
        conversations = (
            Conversation.objects.filter(contact_id=OuterRef("pk"), lifecycle=lifecycle)
            .order_by()
            .values("contact_id")
            .annotate(total=Count("id"))
            .values("total")
        )
    return Coalesce(Subquery(conversations, output_field=IntegerField()), Value(0))


def clients_queryset(organization_id: int, params) -> QuerySet[Contact]:
    """Список контактов (кадры K1/K2): фильтры, поиск и порядок — на сервере.

    Клиент — контакт, который писал: у него есть хотя бы один диалог.
    """
    conversation_qs = Conversation.objects.select_related(
        "channel", "connection", "assigned_operator"
    ).order_by("-last_activity_at")
    identity_qs = ConnectionIdentity.objects.select_related("connection")
    contacts = (
        Contact.objects.filter(organization_id=organization_id, merged_into__isnull=True)
        .annotate(
            last_activity=Subquery(
                Conversation.objects.filter(contact_id=OuterRef("pk"))
                .order_by("-last_activity_at")
                .values("last_activity_at")[:1]
            ),
            open_dialogs_count=_client_counts(lifecycle=LifecycleState.OPEN),
            total_dialogs_count=_client_counts(),
        )
        .filter(last_activity__isnull=False)
        # Связанное подтягивается уже для страницы: prefetch выполняется после
        # среза, а не по всей организации.
        .prefetch_related(
            Prefetch("conversations", queryset=conversation_qs),
            Prefetch("identities", queryset=identity_qs),
        )
    )
    query = params.get("q", "").strip()
    if query:
        contacts = contacts.filter(
            Q(name__icontains=query)
            | Q(phone__icontains=query)
            | Q(identities__username__icontains=query)
            | Q(identities__external_user_id__icontains=query)
        )
    agents = [value for value in params.getlist("agent") if value.isdigit()]
    if agents:
        contacts = contacts.filter(conversations__channel_id__in=agents)
    providers = [
        PROVIDER_BY_CODE[code] for code in params.getlist("channel") if code in PROVIDER_BY_CODE
    ]
    if providers:
        contacts = contacts.filter(conversations__connection__provider__in=providers)
    if params.get("open") == "1":
        contacts = contacts.filter(open_dialogs_count__gt=0)
    field = "open_dialogs_count" if params.get("sort") == "open" else "last_activity"
    ascending = params.get("dir") == "asc"
    return contacts.distinct().order_by(f"{'' if ascending else '-'}{field}", "-id")


def client_row(contact: Contact) -> dict:
    """Строка списка контактов. Связанные диалоги и identity приходят из prefetch."""
    conversations = list(contact.conversations.all())
    channels: set[str] = set()
    agents: dict[int, dict[str, object]] = {}
    for conversation in conversations:
        provider = conversation.connection.provider if conversation.connection_id else None
        if provider in PROVIDER_CODE:
            channels.add(PROVIDER_CODE[provider])
        # Агент = карточка канала обработки: по нему фильтруется список (кадр K1).
        agents.setdefault(
            conversation.channel_id,
            {"id": conversation.channel_id, "code": conversation.channel.code, "name": conversation.channel.name},
        )
    latest = conversations[0]
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
        "email": contact.email or next(
            (
                identity.external_user_id
                for identity in contact.identities.all()
                if identity.connection.provider == "EMAIL"
            ),
            "",
        ),
        # Первый непустой @логин среди identity каналов (остальные — в карточке).
        "username": next((identity.username for identity in contact.identities.all() if identity.username), ""),
        "channels": sorted(channels),
        "openDialogs": contact.open_dialogs_count,
        "totalDialogs": contact.total_dialogs_count,
        "lastActivityAt": latest.last_activity_at.isoformat(),
        "mode": _mode(latest),
        # Колонка «Последний диалог» (кадр K1): кто ведёт — агент или сотрудник.
        "lastAgentName": latest.channel.name,
        "lastAgentCode": latest.channel.code,
        "lastAssignee": _actor_name(latest.assigned_operator),
        "agents": sorted(agents.values(), key=lambda item: str(item["name"])),
    }
