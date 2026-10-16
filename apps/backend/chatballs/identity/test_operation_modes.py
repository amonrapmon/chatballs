"""Organization policy, queue transitions and tenant authorization."""

from datetime import timedelta

from django.db import connection, transaction
from django.test import TestCase
from django.utils import timezone

from chatballs.channels.models import Channel
from chatballs.conversations.models import Contact, Conversation
from chatballs.identity.models import AuditEvent, HumanUser, Organization, OrganizationMembership
from chatballs.testing import TenantAPIClient, tenant_context_for


class OperationModeTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Example", slug="mode")
        self.owner = HumanUser.objects.create_user(email="owner@mode.test", password="test")
        OrganizationMembership.objects.create(organization=self.organization, user=self.owner, role="OWNER")
        self.context = tenant_context_for(self.owner)
        self.channel = Channel.objects.create(organization=self.organization, name="Route", code="route")
        self.contact = Contact.objects.create(organization=self.organization, name="Customer")
        self.client = TenantAPIClient()
        self.client.force_authenticate(self.owner)

    def conversation(self, **kwargs):
        return Conversation.objects.create(organization=self.organization, channel=self.channel,
                                           contact=self.contact, **kwargs)

    def switch(self, mode):
        return self.client.patch("/api/v1/company/administration/", {"operationMode": mode}, format="json")

    def test_transition_is_idempotent_and_preserves_queue_and_human_work(self):
        autonomous = self.conversation(control_mode="AI")
        waiting_since = timezone.now() - timedelta(hours=1)
        waiting = self.conversation(control_mode="PAUSED", waiting_since=waiting_since)
        accepted = self.conversation(control_mode="HUMAN", assigned_operator=self.owner)
        closed = self.conversation(control_mode="AI", lifecycle="CLOSED")
        self.assertEqual(self.switch("OPERATORS_ONLY").status_code, 200)
        self.assertEqual(self.switch("OPERATORS_ONLY").status_code, 200)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.operation_mode_version, 2)
        autonomous.refresh_from_db()
        waiting.refresh_from_db()
        accepted.refresh_from_db()
        closed.refresh_from_db()
        self.assertEqual(autonomous.control_mode, "PAUSED")
        self.assertIsNotNone(autonomous.waiting_since)
        self.assertEqual(autonomous.domain_events.filter(event_type="QUEUE_ENTERED").count(), 1)
        self.assertEqual(waiting.waiting_since, waiting_since)
        self.assertEqual(accepted.assigned_operator_id, self.owner.pk)
        self.assertEqual(accepted.control_mode, "HUMAN")
        self.assertEqual(closed.control_mode, "AI")
        transitions = AuditEvent.objects.filter(payload__has_key="operationMode")
        self.assertEqual(transitions.count(), 1)
        self.assertEqual(transitions.get().payload["operationMode"]["previous"], "AI_AGENTS")
        self.assertEqual(self.switch("AI_AGENTS").status_code, 200)
        autonomous.refresh_from_db()
        self.assertEqual(autonomous.control_mode, "PAUSED")

    def test_employee_and_foreign_member_cannot_switch(self):
        employee = HumanUser.objects.create_user(email="employee@mode.test")
        OrganizationMembership.objects.create(organization=self.organization, user=employee, role="EMPLOYEE")
        self.client.force_authenticate(employee)
        self.assertEqual(self.switch("OPERATORS_ONLY").status_code, 403)
        foreign = Organization.objects.create(name="Other", slug="other-mode")
        foreign_user = HumanUser.objects.create_user(email="foreign@mode.test")
        OrganizationMembership.objects.create(organization=foreign, user=foreign_user, role="ADMIN")
        self.client.force_authenticate(foreign_user)
        response = self.client.patch(f"/api/v1/organizations/{self.organization.public_id}/company/administration/",
                                     {"operationMode": "OPERATORS_ONLY"}, format="json")
        self.assertIn(response.status_code, (403, 404))
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.operation_mode, "AI_AGENTS")

    def test_admin_can_switch_and_invalid_mode_is_atomic(self):
        membership = self.context.membership
        membership.role = "ADMIN"
        membership.save(update_fields=["role"])
        self.assertEqual(self.switch("OPERATORS_ONLY").status_code, 200)
        self.assertEqual(self.switch("UNKNOWN").status_code, 400)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.operation_mode_version, 2)

    def test_transition_only_touches_its_organization(self):
        other = Organization.objects.create(name="Other", slug="other")
        channel = Channel.objects.create(organization=other, code="route", name="Other")
        contact = Contact.objects.create(organization=other, name="Other")
        conversation = Conversation.objects.create(organization=other, channel=channel, contact=contact, control_mode="AI")
        self.switch("OPERATORS_ONLY")
        conversation.refresh_from_db()
        self.assertEqual(conversation.control_mode, "AI")

    def test_mode_transition_works_under_runtime_rls_and_foreign_organization_is_hidden(self):
        from chatballs.identity.operation_modes import change_operation_mode, lock_organization
        from chatballs.tenancy.database import tenant_atomic

        foreign = Organization.objects.create(name="Foreign", slug="foreign-runtime-mode")
        self.conversation(control_mode="AI")
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
                with tenant_atomic(self.context):
                    current = lock_organization(self.organization.pk)
                    change_operation_mode(context=self.context, organization=current, mode="OPERATORS_ONLY")
                    self.assertFalse(Organization.objects.filter(pk=foreign.pk).exists())
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.operation_mode_version, 2)
