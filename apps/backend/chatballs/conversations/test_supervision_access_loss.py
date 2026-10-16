from django.test import TestCase

from chatballs.conversations import test_authorization as visibility_tests
from chatballs.conversations.models import ConversationRead
from chatballs.identity.models import AuditEvent, EmployeeRole, OrganizationMembership
from chatballs.identity.supervision_models import EmployeeGroupSupervision


class SupervisionAccessLossTests(TestCase):
    _employee = visibility_tests.ConversationVisibilityTests._employee
    _conversation = visibility_tests.ConversationVisibilityTests._conversation

    def setUp(self):
        visibility_tests.ConversationVisibilityTests.setUp(self)
        self.supervisor = self._employee("supervisor-loss@test.local", EmployeeRole.SUPERVISOR)
        self.link = EmployeeGroupSupervision.objects.create(employee=self.supervisor, group=self.support)
        self.client.force_authenticate(self.supervisor.user)
        ConversationRead.objects.create(conversation=self.support_conversation, user=self.supervisor.user)

    def revoke(self, **overrides):
        self.link.delete()
        values = {
            "organization": self.organization, "actor": self.owner.user,
            "object_type": "HumanUser", "object_id": str(self.supervisor.user_id),
            "action": "identity.employee_supervised_groups_changed",
            "payload": {"oldGroupIds": [self.support.pk], "groupIds": []},
        }
        values.update(overrides)
        return AuditEvent.objects.create(**values)

    def get_loss(self, conversation=None):
        conversation = conversation or self.support_conversation
        response = self.client.get(f"/api/v1/conversations/{conversation.pk}/")
        self.assertEqual(response.status_code, 404)
        return response.json()

    def test_own_opened_conversation_gets_only_audited_revocation(self):
        event = self.revoke()
        data = self.get_loss()
        self.assertEqual(set(data), {"detail", "supervisionRevoked"})
        self.assertEqual(data["supervisionRevoked"], {
            "groupId": self.support.pk, "groupName": self.support.name,
            "actorName": self.owner.user.email, "occurredAt": event.created_at.isoformat(),
        })
        action = self.client.post(f"/api/v1/conversations/{self.support_conversation.pk}/note/", {"note": "Denied"})
        self.assertEqual(action.status_code, 404)
        self.support_conversation.refresh_from_db()
        self.assertEqual(self.support_conversation.note, "")

    def test_direct_id_and_another_employee_audit_do_not_disclose_revocation(self):
        self.revoke(object_id=str(self.employee.user_id))
        self.assertNotIn("supervisionRevoked", self.get_loss())
        self.assertNotIn("supervisionRevoked", self.get_loss(self.operators_conversation))

    def test_no_prior_read_gets_no_metadata(self):
        self.revoke()
        ConversationRead.objects.filter(user=self.supervisor.user).delete()
        self.assertNotIn("supervisionRevoked", self.get_loss())

    def test_blocked_membership_and_denied_audit_do_not_disclose_metadata(self):
        from django.utils import timezone

        from chatballs.conversations.supervision_access_loss import supervision_access_loss
        from chatballs.tenancy.context import TenantContext

        self.revoke(result="DENIED")
        self.assertNotIn("supervisionRevoked", self.get_loss())
        OrganizationMembership.objects.filter(pk=self.supervisor.pk).update(blocked_at=timezone.now())
        self.assertIsNone(supervision_access_loss(TenantContext.for_membership(self.supervisor), self.support_conversation.pk))

    def test_foreign_tenant_has_no_revocation_metadata(self):
        self.revoke()
        other = self.organization.__class__.objects.create(name="Other", slug="loss-other")
        from chatballs.conversations.supervision_access_loss import supervision_access_loss
        from chatballs.tenancy.context import TenantContext
        foreign_member = OrganizationMembership.objects.create(organization=other, user=self.supervisor.user, role="SUPERVISOR")
        self.assertIsNone(supervision_access_loss(TenantContext.for_membership(foreign_member), self.support_conversation.pk))
