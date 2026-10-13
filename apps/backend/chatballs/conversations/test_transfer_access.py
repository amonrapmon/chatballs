from uuid import uuid4

from django.utils import timezone

from chatballs.conversations.models import Conversation, Message
from chatballs.conversations.selectors import conversation_is_visible
from chatballs.conversations.transfer_operation_test_base import TransferOperationTestBase
from chatballs.conversations.transfer_services import disable_reason, save_reason
from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.events.services import tenant_context_for_event
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import EmployeeRole, OrganizationMembership
from chatballs.identity.supervision_models import EmployeeGroupSupervision
from chatballs.notifications.delivery import _message_text
from chatballs.notifications.models import Notification
from chatballs.notifications.recipients import recipient_user_ids
from chatballs.notifications.selectors import visible_for
from chatballs.tenancy.context import TenantContext


class TransferAccessTests(TransferOperationTestBase):
    def history_url(self, conversation=None):
        return f"{self.root}{(conversation or self.conversation).pk}/transfers/"

    def private_group(self):
        group = EmployeeGroup.objects.create(organization=self.organization, name="Private")
        self.conversation.group = group
        self.conversation.save(update_fields=["group"])
        return group

    def test_paginated_history_preserves_original_snapshot_and_all_attribution(self):
        first = self.post().json()["transfer"]
        save_reason(context=self.context, reason_id=self.reason.pk,
                    data={"name": "Renamed", "code": "renamed"})
        second = self.post(userId=self.members[EmployeeRole.SUPERVISOR].user_id,
                           expectedVersion=1, operationId=str(uuid4())).json()["transfer"]
        disable_reason(context=self.context, reason_id=self.reason.pk)
        response = self.client.get(self.history_url() + "?pageSize=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(response.data["pageCount"], 2)
        older = self.client.get(self.history_url() + "?pageSize=1&page=2").data["items"]
        for displayed, original in ((response.data["items"][0], second), (older[0], first)):
            snapshot = {key: displayed[key] for key in original}
            snapshot["reason"] = {key: displayed["reason"][key] for key in original["reason"]}
            self.assertEqual(snapshot, original)
            self.assertFalse(displayed["reason"]["isActive"])
            self.assertEqual(displayed["reason"]["currentName"], "Renamed")
            self.assertEqual(displayed["initiatedBy"]["id"], original["initiatedById"])
        self.assertEqual(first["initiatedById"], self.context.actor_user.pk)
        self.assertEqual(first["previousOperatorId"], self.members[EmployeeRole.ADMIN].user_id)
        self.assertEqual(first["newOperatorId"], self.data["userId"])
        detail = self.client.get(self.history_url() + f"{first['id']}/")
        self.assertEqual(detail.data["transfer"], older[0])
        self.assertEqual(first["reason"]["name"], "Specialist needed")
        self.assertEqual(first["comment"], self.data["comment"])

    def test_assignment_grants_access_but_later_loss_denies_history_detail_and_replay(self):
        self.private_group()
        employee = self.members[EmployeeRole.EMPLOYEE]
        self.assertFalse(conversation_is_visible(actor=employee, conversation=self.conversation))
        row = self.post().json()["transfer"]
        self.conversation.refresh_from_db()
        self.assertTrue(conversation_is_visible(actor=employee, conversation=self.conversation))
        self.client.force_authenticate(employee.user)
        self.assertEqual(self.client.get(self.history_url()).status_code, 200)
        self.client.force_authenticate(self.context.actor_user)
        self.assertEqual(self.post(userId=self.members[EmployeeRole.SUPERVISOR].user_id,
                                   expectedVersion=1, operationId=str(uuid4())).status_code, 200)
        self.client.force_authenticate(employee.user)
        for url in (self.history_url(), self.history_url() + f"{row['id']}/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn(self.data["comment"], str(response.data))
        self.assertEqual(self.post().status_code, 404)

    def test_foreign_tenant_direct_id_and_anonymous_cannot_read_comment(self):
        row = self.post().json()["transfer"]
        for user in (self.foreign_user, None):
            self.client.force_authenticate(user)
            for url in (self.history_url(), self.history_url() + f"{row['id']}/"):
                response = self.client.get(url)
                self.assertIn(response.status_code, (401, 403, 404))
                self.assertNotIn(self.data["comment"].encode(), response.content)
        self.client.force_authenticate(self.context.actor_user)
        response = self.client.get(self.history_url(self.foreign_conversation) + f"{row['id']}/")
        self.assertEqual(response.status_code, 404)

    def test_supervisor_can_transfer_only_in_current_control_area(self):
        group = self.private_group()
        supervisor = self.members[EmployeeRole.SUPERVISOR]
        link = EmployeeGroupSupervision.objects.create(employee=supervisor, group=group)
        self.client.force_authenticate(supervisor.user)
        self.assertEqual(self.post().status_code, 200)
        link.delete()
        for response in (self.client.get(self.history_url()), self.post()):
            self.assertEqual(response.status_code, 404)
            self.assertNotIn(self.data["comment"], str(response.data))

    def test_operator_options_are_active_tenant_scoped_and_require_assignment_access(self):
        employee = self.members[EmployeeRole.EMPLOYEE]
        self.client.force_authenticate(employee.user)
        url = f"{self.root}{self.conversation.pk}/transfer-options/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data["items"]], [self.reason.pk])
        disable_reason(context=self.context, reason_id=self.reason.pk)
        self.assertEqual(self.client.get(url).data["items"], [])
        self.private_group()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_notification_is_addressed_filtered_by_current_access_and_retries_do_not_reassign(self):
        self.private_group()
        self.assertEqual(self.post().status_code, 200)
        notification = Notification.objects.get()
        employee = self.members[EmployeeRole.EMPLOYEE]
        context = TenantContext.for_membership(employee)
        self.assertEqual(recipient_user_ids(notification), [employee.user_id])
        self.assertEqual(list(visible_for(context).values_list("pk", flat=True)), [notification.pk])
        self.assertFalse(visible_for(self.context).exists())
        event = OutboxEvent.objects.get()
        # Removing the initiator does not invalidate the recipient delivery context.
        OrganizationMembership.objects.filter(pk=self.context.membership_id).update(blocked_at=timezone.now())
        delivery_context = tenant_context_for_event(event)
        self.assertIsNone(delivery_context.membership)
        for _ in range(2):
            dispatch(event)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assignment_version, 1)
        self.assertEqual(Notification.objects.count(), 1)
        Conversation.objects.filter(pk=self.conversation.pk).update(assigned_operator=None)
        self.assertFalse(recipient_user_ids(notification))
        self.assertFalse(visible_for(context).exists())
        dispatch(event)
        self.conversation.refresh_from_db()
        self.assertIsNone(self.conversation.assigned_operator_id)

    def test_internal_data_never_enters_client_history_ai_or_notification_payloads(self):
        self.assertEqual(self.post().status_code, 200)
        notification = Notification.objects.get()
        from chatballs.ai.models import AIAgent
        from chatballs.ai.runtime import build_turn_messages
        from chatballs.conversations.ai_turn import _history
        from chatballs.conversations.serializers import conversation_payload

        agent = AIAgent.objects.create(organization=self.organization, channel=self.conversation.channel)
        history = _history(self.conversation, agent.history_limit)
        ai = build_turn_messages(agent=agent, message="Hello", history=history,
                                 fragments=[], conversation=self.conversation)
        from chatballs.conversations.models import ConnectionIdentity
        from chatballs.integrations.models import Integration
        from chatballs.webchat.models import WebChatWidget, WebSession
        from chatballs.webchat.message_history import messages_payload

        connection = Integration.objects.create(
            organization=self.organization, channel=self.conversation.channel,
            kind="MESSENGER", provider="WEB", name="Web",
        )
        widget = WebChatWidget.objects.create(organization=self.organization, integration=connection,
                                             code="test", name="Test")
        identity = ConnectionIdentity.objects.create(
            organization=self.organization, connection=connection, contact=self.conversation.contact,
            external_user_id="customer",
        )
        session = WebSession.objects.create(organization=self.organization, connection=connection,
                                           widget=widget, identity=identity, token_hash="a" * 64)
        representations = [
            messages_payload(session, 0),
            list(Message.objects.values()), conversation_payload(self.conversation, detailed=True),
            ai, notification.__dict__, list(OutboxEvent.objects.values()),
            _message_text(notification, language="en"),
        ]
        for data in representations:
            self.assertNotIn(self.data["comment"], str(data))
            self.assertNotIn(self.reason.name, str(data))
        self.assertIn("transferred", _message_text(notification, language="en"))
        self.assertIn("передан", _message_text(notification, language="ru"))
