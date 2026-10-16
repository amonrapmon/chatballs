"""Общая сцена тестов правил: диалог ждёт в очереди, есть кому его назначить."""

from django.utils import timezone

from chatballs.channels.models import Channel
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.models import (
    ConnectionIdentity,
    Contact,
    ControlMode,
    Conversation,
    ExpectedResponder,
    LifecycleState,
)
from chatballs.conversations.rules.models import RuleExecution
from chatballs.conversations.rules.scheduler import RULE_EXECUTION_DUE
from chatballs.conversations.rules.settings import update_rule
from chatballs.conversations.services import assign_operator
from chatballs.conversations.transports.base import InboundMessage
from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.identity.group_models import EmployeeGroup, EmployeeGroupMember
from chatballs.identity.models import (
    EmployeeRole,
    HumanUser,
    Organization,
    OrganizationMembership,
)
from chatballs.identity.supervision_models import EmployeeGroupSupervision
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

    def supervisor(self, name: str, group: EmployeeGroup | None = None) -> OrganizationMembership:
        """Супервизор с группой в области контроля (без неё — с пустой областью)."""
        membership = self.employee(name, EmployeeRole.SUPERVISOR)
        if group is not None:
            EmployeeGroupSupervision.objects.create(employee=membership, group=group)
        return membership

    def enable(self, kind: str, **changes) -> None:
        update_rule(context=self.context, kind=kind, changes={"enabled": True, **changes})

    def receive(self, external_id: str, *, user: str = "client", connection=None) -> Conversation:
        """Сообщение клиента через штатный приём. Возвращает его открытый диалог."""
        connection = connection or self.connection
        ingest_inbound(connection, InboundMessage(
            external_id=external_id, user_id=user, chat_id=user, text="Hello",
            display_name="Client",
        ))
        contact = ConnectionIdentity.objects.get(
            connection=connection, external_user_id=user
        ).contact
        return Conversation.objects.filter(contact=contact).latest("id")

    def assign(
        self, membership: OrganizationMembership | None, conversation: Conversation | None = None
    ) -> RuleExecution | None:
        """Назначить ответственного и вернуть поставленный этим возврат."""
        conversation = conversation or self.conversation
        assign_operator(
            context=self.context,
            conversation_id=conversation.pk,
            assignee=membership.user if membership else None,
        )
        return self.executions(conversation).order_by("-id").first() if membership else None

    def executions(self, conversation: Conversation | None = None):
        return RuleExecution.objects.filter(conversation=conversation or self.conversation)

    def due_events(self, execution: RuleExecution | None = None):
        events = OutboxEvent.objects.filter(event_type=RULE_EXECUTION_DUE).order_by("created_at")
        if execution is not None:
            events = events.filter(aggregate_id=str(execution.pk))
        return events

    def deliver(self, execution: RuleExecution) -> None:
        """Отдать исполнителю все события записи, как это сделал бы воркер."""
        for event in self.due_events(execution):
            dispatch(event)
