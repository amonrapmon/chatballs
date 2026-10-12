"""Recipient directory: availability, presence and dialogue load are independent."""

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.api.permissions import HasCapability
from chatballs.conversations.models import Conversation, LifecycleState
from chatballs.identity.avatars import user_avatar_url
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.work_status_access import directory_memberships
from chatballs.identity.work_status_payloads import status_payload
from chatballs.presence import ONLINE_WITHIN_SECONDS, last_seen

# Справочник выбора: ростер организации может быть большим, поэтому список
# коллег ограничен и ищется на сервере — в выборе стоит строка поиска (кадр G).
DIRECTORY_LIMIT = 50


class ConversationDirectoryView(APIView):
    """Справочник блока «Диалог» для оператора (дизайн-базлайн v2, кадр G):
    все группы организации — для переноса, активные коллеги — для назначения.
    Доступен любому, кто видит чат: менеджерские списки сотрудников и групп
    сотруднику закрыты, а переносить и назначать он может."""

    permission_classes = [HasCapability]
    required_capabilities = {"GET": "conversations.view"}

    def get(self, request: Request) -> Response:
        organization_id = request.tenant_context.organization_id
        groups = EmployeeGroup.objects.filter(organization_id=organization_id).order_by("name")
        members = (
            directory_memberships(organization_id)
            .order_by("user__full_name", "user__email")
        )
        query = request.query_params.get("q", "").strip()
        if query:
            members = members.filter(
                Q(user__full_name__icontains=query) | Q(user__email__icontains=query)
            )
        # Ответственного можно назначить и вне выдачи — по поиску, поэтому
        # оставшихся не прячем молча, а сообщаем признаком hasMore.
        rows = list(members[: DIRECTORY_LIMIT + 1])
        shown = rows[:DIRECTORY_LIMIT]
        # Присутствие и загрузка — второй и третий признак при выборе
        # ответственного (макет «Очередь и уведомления», кадр Q5). Назначить
        # отсутствующего можно: признак приблизительный и ничего не запрещает.
        user_ids = [member.user_id for member in shown]
        seen = last_seen(organization_id, user_ids)
        now = timezone.now()
        load = dict(
            Conversation.objects.filter(
                organization_id=organization_id,
                lifecycle=LifecycleState.OPEN,
                assigned_operator_id__in=user_ids,
            )
            .values_list("assigned_operator_id")
            .annotate(total=Count("id"))
        )
        return Response(
            {
                "groups": [{"id": group.id, "name": group.name, "color": group.color} for group in groups],
                "employees": [
                    {
                        "id": member.user_id,
                        "name": member.user.full_name or member.user.email,
                        "avatarUrl": user_avatar_url(member.user, request.tenant_context.organization.public_id),
                        "role": member.role,
                        "workStatus": status_payload(member),
                        "online": member.user_id in seen
                        and (now - seen[member.user_id]).total_seconds() <= ONLINE_WITHIN_SECONDS,
                        "lastSeenAt": (
                            seen[member.user_id].isoformat() if member.user_id in seen else None
                        ),
                        "openDialogs": load.get(member.user_id, 0),
                    }
                    for member in shown
                ],
                "hasMoreEmployees": len(rows) > DIRECTORY_LIMIT,
            }
        )


