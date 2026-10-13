"""Общая сцена тестов правил: диалог ждёт в очереди, есть кому его назначить."""

from django.utils import timezone

from chatballs.channels.models import Channel
from chatballs.conversations.models import (
    Contact,
    ControlMode,
    Conversation,
    ExpectedResponder,
    LifecycleState,
)
from chatballs.conversations.rules.models import RuleExecution
from chatballs.conversations.rules.scheduler import RULE_EXECUTION_DUE
from chatballs.conversations.services import assign_operator
from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.identity.group_models import EmployeeGroup, EmployeeGroupMember
from chatballs.identity.models import (
    EmployeeRole,
    HumanUser,
    Organization,
    OrganizationMembership,
)
from chatballs.integrations.models import Integration
from chatballs.testing import tenant_context_for


class RuleScene:
    """Примесь: данные создаются в setUp, чтобы подходить и TransactionTestCase."""

    slug = "handling-rules"

    def setUp(self) -> None:
        super().setUp()
        self.organization = Organization.objects.create(name="Rules", slug=self.slug)
        self.group = EmployeeGroup.objects.create(organization=self.organization, name="Support")
        self.owner = self.employee("owner", EmployeeRole.OWNER)
        self.operator = self.employee("operator", EmployeeRole.EMPLOYEE)
        self.colleague = self.employee("colleague", EmployeeRole.EMPLOYEE)
        self.context = tenant_context_for(self.owner.user, self.organization)
        self.channel = Channel.objects.create(
            organization=self.organization, group=self.group, code="rules", name="Rules"
        )
        self.connection = Integration.objects.create(
            organization=self.organization, kind="MESSENGER", provider="WEB", name="Web",
            channel=self.channel,
        )
        self.conversation = Conversation.objects.create(
            organization=self.organization,
            channel=self.channel,
            connection=self.connection,
            group=self.group,
            contact=Contact.objects.create(organization=self.organization, name="Customer"),
            lifecycle=LifecycleState.OPEN,
            control_mode=ControlMode.PAUSED,
            expected_responder=ExpectedResponder.OPERATOR,
            waiting_since=timezone.now(),
        )

    def employee(self, name: str, role: str) -> OrganizationMembership:
        user = HumanUser.objects.create_user(email=f"{name}@{self.slug}.test")
        membership = OrganizationMembership.objects.create(
            user=user, organization=self.organization, role=role
        )
        if role == EmployeeRole.EMPLOYEE:
            EmployeeGroupMember.objects.create(
                organization=self.organization, group=self.group, employee=membership
            )
        return membership

    def assign(self, membership: OrganizationMembership | None) -> RuleExecution | None:
        """Назначить ответственного и вернуть поставленный этим возврат."""
        assign_operator(
            context=self.context,
            conversation_id=self.conversation.pk,
            assignee=membership.user if membership else None,
        )
        return self.executions().order_by("-id").first() if membership else None

    def executions(self):
        return RuleExecution.objects.filter(conversation=self.conversation)

    def due_events(self, execution: RuleExecution | None = None):
        events = OutboxEvent.objects.filter(event_type=RULE_EXECUTION_DUE).order_by("created_at")
        if execution is not None:
            events = events.filter(aggregate_id=str(execution.pk))
        return events

    def deliver(self, execution: RuleExecution) -> None:
        """Отдать исполнителю все события записи, как это сделал бы воркер."""
        for event in self.due_events(execution):
            dispatch(event)
