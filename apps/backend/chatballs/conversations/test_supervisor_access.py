from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from chatballs.conversations import test_authorization as visibility_tests
from chatballs.conversations.access import require_conversation_action
from chatballs.conversations.assignment import assign_operator
from chatballs.conversations.models import Conversation
from chatballs.conversations.participant_models import ConversationParticipant
from chatballs.conversations.selectors import (
    conversation_is_visible,
    visible_conversations_for,
)
from chatballs.identity.models import EmployeeRole, OrganizationMembership
from chatballs.identity.policy import get_effective_access, require_capability
from chatballs.identity.supervision_models import EmployeeGroupSupervision
from chatballs.notifications.delivery import deliver_notification
from chatballs.notifications.models import (
    Notification,
    NotificationAudience,
    NotificationType,
)
from chatballs.notifications.recipients import recipient_user_ids
from chatballs.notifications.selectors import visible_for
from chatballs.tenancy.context import TenantContext


class SupervisorAccessTests(TestCase):
    _employee = visibility_tests.ConversationVisibilityTests._employee
    _conversation = visibility_tests.ConversationVisibilityTests._conversation

    def setUp(self):
        visibility_tests.ConversationVisibilityTests.setUp(self)
        self.supervisor = self._employee("supervisor@conversation.test", EmployeeRole.SUPERVISOR)
        self.link = EmployeeGroupSupervision.objects.create(employee=self.supervisor, group=self.support)
        self.context = TenantContext.for_membership(self.supervisor)
        self.client.force_authenticate(self.supervisor.user)

    def url(self, conversation=None, action=""):
        conversation = conversation or self.support_conversation
        return f"/api/v1/conversations/{conversation.pk}/{action}"

    def test_control_is_separate_from_work_and_grants_only_explicit_actions(self):
        self.assertTrue(conversation_is_visible(actor=self.supervisor, conversation=self.support_conversation))
        access = self.client.get(self.url()).json()["conversation"]["access"]
        self.assertTrue(access["supervised"])
        self.assertEqual(set(access["actions"]), {
            "conversations.view", "conversations.assign", "conversations.transfer",
            "conversations.participants", "conversations.comment",
        })
        for action in ("claim/", "close/", "release/", "spam/", "return-queue/"):
            with self.subTest(action=action):
                self.assertEqual(self.client.post(self.url(action=action)).status_code, 404)
        self.assertEqual(self.client.delete(self.url()).status_code, 404)
        self.assertEqual(self.client.post(self.url(action="note/"), {"note": "Internal"}, format="json").status_code, 200)
        self.assertEqual(self.client.post(self.url(action="assignee/"), {"userId": self.employee.user_id}, format="json").status_code, 200)
        self.assertEqual(self.client.post(self.url(action="group/"), {"groupId": self.operators.pk}, format="json").status_code, 200)
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_empty_area_and_ungrouped_preserve_only_ordinary_work(self):
        self.link.delete()
        ids = set(visible_conversations_for(self.context).values_list("id", flat=True))
        self.assertEqual(ids, {self.shared_conversation.pk})
        self.assertEqual(get_effective_access(self.supervisor)["supervisionCapabilities"], [])
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        access = self.client.get(self.url(self.shared_conversation)).json()["conversation"]["access"]
        self.assertFalse(access["supervised"])
        self.assertIn("conversations.operate", access["actions"])

    def test_revocation_uses_current_role_with_stale_context(self):
        OrganizationMembership.objects.filter(pk=self.supervisor.pk).update(role=EmployeeRole.EMPLOYEE)
        self.assertFalse(require_capability(self.supervisor, "conversations.assign", self.support_conversation))
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        with self.assertRaises(Conversation.DoesNotExist):
            assign_operator(context=self.context, conversation_id=self.support_conversation.pk, assignee=self.employee.user)
        self.support_conversation.refresh_from_db()
        self.assertIsNone(self.support_conversation.assigned_operator_id)

    def test_assignment_retry_rechecks_revoked_supervision(self):
        operation = uuid4()
        assign_operator(context=self.context, conversation_id=self.support_conversation.pk,
                        assignee=self.employee.user, operation_id=operation)
        self.link.delete()
        with self.assertRaises(Conversation.DoesNotExist):
            assign_operator(context=self.context, conversation_id=self.support_conversation.pk,
                            assignee=self.employee.user, operation_id=operation)
        self.assertEqual(self.support_conversation.domain_events.count(), 1)

    def test_scope_revocation_keeps_independent_assignment_and_participation(self):
        self.operators_conversation.assigned_operator = self.supervisor.user
        self.operators_conversation.save(update_fields=["assigned_operator"])
        row = ConversationParticipant.objects.create(
            conversation=self.support_conversation, membership=self.supervisor,
            joined_by=self.owner, join_reason="Consultation",
        )
        self.link.delete()
        self.assertTrue(require_capability(self.supervisor, "conversations.operate", self.support_conversation))
        ids = set(visible_conversations_for(self.context).values_list("id", flat=True))
        self.assertEqual(ids, {self.support_conversation.pk, self.operators_conversation.pk, self.shared_conversation.pk})
        row.left_at, row.left_by, row.leave_reason = timezone.now(), self.owner, "Finished"
        row.save()
        self.assertFalse(conversation_is_visible(actor=self.supervisor, conversation=self.support_conversation))

    def test_direct_service_and_foreign_tenant_never_expand_scope(self):
        with self.assertRaises(Conversation.DoesNotExist):
            assign_operator(context=self.context, conversation_id=self.operators_conversation.pk, assignee=self.supervisor.user)
        self.assertFalse(require_capability(self.supervisor, "conversations.assign", self.operators_conversation))
        foreign = self.owner.organization.__class__.objects.create(name="Other", slug="supervision-other")
        foreign_actor = OrganizationMembership.objects.create(organization=foreign, user=self.supervisor.user, role="OWNER")
        self.assertFalse(conversation_is_visible(actor=foreign_actor, conversation=self.support_conversation))
        with self.assertRaises(Conversation.DoesNotExist):
            require_conversation_action(TenantContext.for_membership(foreign_actor), self.support_conversation, "conversations.assign")

    def test_history_and_counters_do_not_disclose_inaccessible_dialogs(self):
        self.operators_conversation.contact = self.support_conversation.contact
        self.operators_conversation.save(update_fields=["contact"])
        history = self.client.get(self.url()).json()["conversation"]["history"]
        self.assertNotIn(self.operators_conversation.pk, {item["id"] for item in history})
        counters = self.client.get("/api/v1/conversations/counters/")
        self.assertEqual(counters.status_code, 200)
        self.assertNotIn(self.operators.pk, {item["id"] for item in counters.json()["groups"]})
        detail = self.client.get(f"/api/v1/conversations/clients/{self.support_conversation.contact_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual({item["id"] for item in detail.json()["client"]["dialogs"]}, {self.support_conversation.pk})
        stats = self.client.get("/api/v1/conversations/stats/").json()
        self.assertEqual(stats["ops"]["openDialogs"], 2)
        self.assertEqual(stats["period"]["dialogs"], 2)
        self.assertNotIn(self.operators_conversation.pk, {item["conversationId"] for item in stats["problems"]})

    def test_contact_id_and_search_do_not_bypass_conversation_scope(self):
        response = self.client.get(f"/api/v1/conversations/clients/{self.operators_conversation.contact_id}/")
        self.assertEqual(response.status_code, 404)
        contacts = self.client.get("/api/v1/conversations/clients/").json()["items"]
        self.assertEqual({item["id"] for item in contacts}, {self.support_conversation.contact_id, self.shared_conversation.contact_id})
        self.link.delete()
        self.assertEqual(self.client.get(f"/api/v1/conversations/clients/{self.support_conversation.contact_id}/").status_code, 404)

    def test_directory_keeps_work_status_and_limits_load_to_current_visibility(self):
        from chatballs.identity.work_status_codes import WorkStatus
        from chatballs.identity.work_status_services import change_work_status

        operation = change_work_status(
            context=TenantContext.for_membership(self.employee),
            status=WorkStatus.BREAK, expected_version=0, operation_id=uuid4(),
        )
        for conversation in (self.support_conversation, self.operators_conversation):
            conversation.assigned_operator = self.employee.user
            conversation.save(update_fields=["assigned_operator"])
        url = "/api/v1/conversations/directory/"
        rows = {row["id"]: row for row in self.client.get(url).json()["employees"]}
        self.assertEqual(rows[self.employee.user_id]["openDialogs"], 1)
        expected_status = {
            "status": WorkStatus.BREAK, "version": 1,
            "changedAt": operation.changed_at.isoformat(),
        }
        self.assertEqual(rows[self.employee.user_id]["workStatus"], expected_status)
        self.link.delete()
        rows = {row["id"]: row for row in self.client.get(url).json()["employees"]}
        self.assertEqual(rows[self.employee.user_id]["openDialogs"], 0)
        self.assertEqual(rows[self.employee.user_id]["workStatus"], expected_status)

    def test_runtime_role_applies_supervision_and_tenant_boundary(self):
        from django.db import connection, transaction

        from chatballs.tenancy.database import tenant_atomic

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            with tenant_atomic(self.context):
                self.assertEqual(
                    set(visible_conversations_for(self.context).values_list("pk", flat=True)),
                    {self.support_conversation.pk, self.shared_conversation.pk},
                )
                self.assertTrue(require_capability(self.supervisor, "conversations.participants", self.support_conversation))
                self.assertFalse(require_capability(self.supervisor, "conversations.assign", self.operators_conversation))

    def test_admin_secrets_settings_and_colleague_accounts_are_denied(self):
        for path in ("integrations/", "company/administration/", "company/administration/audit/", "employees/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(f"/api/v1/{path}").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/instance/settings/").status_code, 403)
        self.assertEqual(self.client.post("/api/v1/employees/operators/", {}, format="json").status_code, 403)
        for member in (self.supervisor, self.employee):
            for action in ("update/", "reset-password/", "revoke-sessions/", "block/", "transfer-ownership/"):
                with self.subTest(member=member.pk, action=action):
                    self.assertEqual(self.client.post(f"/api/v1/employees/{member.user_id}/{action}", {}, format="json").status_code, 403)

    def notification(self):
        return Notification.objects.create(
            organization=self.organization, type=NotificationType.OPERATOR_REQUESTED,
            audience=NotificationAudience.OPERATORS, audience_group=self.support,
            source_type="Conversation", source_id=str(self.support_conversation.pk), title="Internal",
        )

    def test_background_and_notification_reads_recheck_scope_and_source(self):
        notification = self.notification()
        self.assertIn(self.supervisor.user_id, recipient_user_ids(notification))
        self.assertTrue(visible_for(self.context).filter(pk=notification.pk).exists())
        self.link.delete()
        self.assertNotIn(self.supervisor.user_id, recipient_user_ids(notification))
        self.assertFalse(visible_for(self.context).filter(pk=notification.pk).exists())
        self.assertEqual(deliver_notification(notification, user_ids=[self.supervisor.user_id]), 0)
        # Stored audience_group must not authorize a source that has since moved.
        EmployeeGroupSupervision.objects.create(employee=self.supervisor, group=self.support)
        self.support_conversation.group = self.operators
        self.support_conversation.save(update_fields=["group"])
        self.assertNotIn(self.supervisor.user_id, recipient_user_ids(notification))
        self.assertFalse(visible_for(self.context).filter(pk=notification.pk).exists())

    def test_blocking_and_deactivation_revoke_stale_context(self):
        notification = self.notification()
        self.supervisor.block()
        self.assertFalse(conversation_is_visible(actor=self.supervisor, conversation=self.shared_conversation))
        self.assertEqual(list(visible_for(self.context)), [])
        self.assertNotIn(self.supervisor.user_id, recipient_user_ids(notification))

    def test_background_rechecks_role_and_direct_audience_membership(self):
        notification = self.notification()
        notification.audience = NotificationAudience.USER
        notification.recipient_user = self.supervisor.user
        notification.save(update_fields=["audience", "recipient_user"])
        self.assertEqual(recipient_user_ids(notification), [self.supervisor.user_id])
        OrganizationMembership.objects.filter(pk=self.supervisor.pk).update(role=EmployeeRole.EMPLOYEE)
        self.assertEqual(recipient_user_ids(notification), [])
        self.assertFalse(visible_for(self.context).filter(pk=notification.pk).exists())
        self.assertEqual(deliver_notification(notification, user_ids=[self.supervisor.user_id]), 0)

    def test_merged_internal_comments_allow_control_without_public_reply_rights(self):
        from rest_framework.exceptions import NotFound

        from chatballs.conversations.comment_services import create_comment

        body = {"audience": "INTERNAL", "text": "Internal review", "operationId": str(uuid4())}
        response = self.client.post(self.url(action="comments/"), body, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(self.client.get(self.url(action="comments/")).json()["items"]), 1)
        self.assertEqual(self.client.get(self.url(action="messages/")).json()["items"], [])
        self.assertEqual(self.client.post(self.url(action="messages/"), {"text": "Reply"}, format="json").status_code, 404)
        self.assertEqual(self.client.post(self.url(action="reply-assistance/"), {"operationKey": "review"}, format="json").status_code, 403)
        self.assertEqual(self.client.get(self.url(action="diagnostic/")).status_code, 403)
        self.link.delete()
        self.assertEqual(self.client.get(self.url(action="comments/")).status_code, 404)
        self.assertEqual(self.client.post(self.url(action="comments/"), body, format="json").status_code, 404)
        with self.assertRaises(NotFound):
            create_comment(context=self.context, conversation_id=self.support_conversation.pk,
                           audience="INTERNAL", text="Denied", operation_id=uuid4())

    def test_merged_directory_preserves_status_but_scopes_colleague_dialog_load(self):
        Conversation.objects.filter(pk__in=[self.support_conversation.pk, self.operators_conversation.pk]).update(
            assigned_operator=self.employee.user,
        )
        response = self.client.get("/api/v1/conversations/directory/")
        self.assertEqual(response.status_code, 200)
        colleague = next(row for row in response.json()["employees"] if row["id"] == self.employee.user_id)
        self.assertIn("workStatus", colleague)
        self.assertEqual(colleague["openDialogs"], 1)
        self.link.delete()
        colleague = next(row for row in self.client.get("/api/v1/conversations/directory/").json()["employees"]
                         if row["id"] == self.employee.user_id)
        self.assertEqual(colleague["openDialogs"], 0)
        self.assertEqual(self.client.get("/api/v1/conversations/templates/").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/conversations/templates/", {}, format="json").status_code, 403)
