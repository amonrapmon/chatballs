"""Сцена тестов уведомлений правил: супервизоры своей и чужой группы."""

from uuid import uuid4

from chatballs.conversations.rules.rule_test_base import RuleScene
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import OrganizationMembership
from chatballs.identity.work_status_services import change_work_status
from chatballs.notifications.models import Notification
from chatballs.testing import tenant_context_for


class NotificationScene(RuleScene):
    def setUp(self) -> None:
        super().setUp()
        self.lead = self.supervisor("lead", self.group)
        other_group = EmployeeGroup.objects.create(organization=self.organization, name="Sales")
        self.outsider = self.supervisor("outsider", other_group)

    def as_user(self, membership: OrganizationMembership):
        return tenant_context_for(membership.user, self.organization)

    def notices(self, key: str):
        return Notification.objects.filter(organization=self.organization, title_key=key)

    def notified(self, key: str) -> set[int]:
        return set(self.notices(key).values_list("recipient_user_id", flat=True))

    def status(self, execution) -> tuple[str, str]:
        execution.refresh_from_db()
        return execution.status, execution.reason

    def make_ready(self, membership: OrganizationMembership) -> None:
        change_work_status(
            context=self.as_user(membership), status="READY", expected_version=0,
            operation_id=uuid4(),
        )
