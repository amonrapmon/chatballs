from dataclasses import replace

from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from chatballs.conversations.models import ControlMode, Conversation, MessageAuthor
from chatballs.conversations.participant_services import add_participant, remove_participant
from chatballs.conversations.participant_test_base import ParticipantTestBase
from chatballs.conversations.services import ClaimError, post_operator_message
from chatballs.identity.group_models import EmployeeGroup, EmployeeGroupMember
from chatballs.identity.models import EmployeeRole, OrganizationMembership
from chatballs.identity.policy import require_capability
from chatballs.identity.supervision_models import EmployeeGroupSupervision
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import TenantAPIClient


class ParticipantWorkflowTests(ParticipantTestBase):
    def setUp(self):
        self.group = EmployeeGroup.objects.create(organization=self.organization, name="Private")
        self.conversation.group = self.group
        self.conversation.control_mode = ControlMode.HUMAN
        self.conversation.save(update_fields=["group", "control_mode"])
        self.client = TenantAPIClient()
        self.client.force_authenticate(self.members[0].user)
        self.base = f"/api/v1/conversations/{self.conversation.pk}/"

    def add(self, **changes):
        return add_participant(**{
            "context": self.context, "conversation_id": self.conversation.pk,
            "membership_id": self.members[1].pk, "reason": "Internal consultation", **changes,
        })

    def remove(self, participant, **changes):
        return remove_participant(**{
            "context": self.context, "conversation_id": self.conversation.pk,
            "participant_id": participant.pk, "reason": "Consultation finished", **changes,
        })

    def test_participant_reads_comments_and_replies_with_own_author_without_takeover(self):
        row, _ = self.add()
        self.client.force_authenticate(self.members[1].user)
        for suffix in ("", "messages/", "participants/", "participants/history/"):
            self.assertEqual(self.client.get(self.base + suffix).status_code, 200)
        note = self.client.post(self.base + "note/", {"note": "Private"}, format="json")
        self.assertEqual(note.status_code, 200)
        reply = self.client.post(self.base + "messages/", {"text": "My answer"}, format="json")
        self.assertEqual(reply.status_code, 201)
        message = self.conversation.messages.get(author_type=MessageAuthor.OPERATOR)
        self.assertEqual(message.author_user_id, self.members[1].user_id)
        self.assertIsNotNone(message.created_at)
        self.assertEqual(reply.json()["message"]["authorUserId"], self.members[1].user_id)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assigned_operator_id, self.members[0].user_id)
        self.assertEqual(self.conversation.note_author_id, self.members[1].user_id)
        for action in ("claim/", "release/", "return-queue/", "close/", "spam/"):
            self.assertEqual(self.client.post(self.base + action).status_code, 409)
        for capability in ("conversations.assign", "conversations.transfer", "conversations.call", "conversations.participants"):
            self.assertFalse(require_capability(self.members[1], capability, self.conversation))
        self.remove(row)
        message.refresh_from_db()
        self.assertEqual(message.author_user_id, self.members[1].user_id)

    def test_revocation_ends_http_and_stale_service_access(self):
        row, _ = self.add()
        context = TenantContext.for_membership(self.members[1])
        self.remove(row)
        self.client.force_authenticate(self.members[1].user)
        for suffix in ("", "messages/", "participants/", "participants/history/"):
            self.assertEqual(self.client.get(self.base + suffix).status_code, 404)
        for suffix, data in (("messages/", {"text": "Denied"}), ("note/", {"note": "Denied"})):
            self.assertEqual(self.client.post(self.base + suffix, data, format="json").status_code, 404)
        with self.assertRaises(Conversation.DoesNotExist):
            post_operator_message(context=context, conversation=self.conversation, text="Stale")

    def test_group_reader_cannot_reply_as_manager_but_real_admin_preserves_assignee(self):
        member = self.members[2]
        EmployeeGroupMember.objects.create(organization=self.organization, group=self.group, employee=member)
        self.client.force_authenticate(member.user)
        response = self.client.post(self.base + "messages/", {"text": "Denied"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.conversation.messages.exists())
        member.role = EmployeeRole.ADMIN
        member.save(update_fields=["role"])
        response = self.client.post(self.base + "messages/", {"text": "Admin answer"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["message"]["authorUserId"], member.user_id)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assigned_operator_id, self.members[0].user_id)

    def test_revocation_preserves_independent_group_assignment_and_management_access(self):
        row, _ = self.add()
        EmployeeGroupMember.objects.create(organization=self.organization, group=self.group, employee=self.members[1])
        self.remove(row)
        self.assertTrue(require_capability(self.members[1], "conversations.view", self.conversation))
        self.assertTrue(require_capability(self.members[0], "conversations.view", self.conversation))
        self.members[2].role = EmployeeRole.ADMIN
        self.members[2].save(update_fields=["role"])
        self.assertTrue(require_capability(self.members[2], "conversations.view", self.conversation))

    def test_participation_only_cannot_claim_ai_or_reply_outside_human(self):
        self.add()
        self.conversation.control_mode = ControlMode.AI
        self.conversation.save(update_fields=["control_mode"])
        context = TenantContext.for_membership(self.members[1])
        with self.assertRaises(ClaimError):
            post_operator_message(context=context, conversation=self.conversation, text="Denied")
        self.client.force_authenticate(self.members[1].user)
        self.assertEqual(self.client.post(self.base + "messages/", {"text": "Denied"}, format="json").status_code, 409)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assigned_operator_id, self.members[0].user_id)

    def test_readers_and_participants_cannot_manage_composition(self):
        row, _ = self.add()
        EmployeeGroupMember.objects.create(organization=self.organization, group=self.group, employee=self.members[2])
        for member in (self.members[2], self.members[1]):
            if member == self.members[1]:
                self.add()
            with self.assertRaises(Conversation.DoesNotExist):
                self.add(context=TenantContext.for_membership(member), membership_id=self.members[0].pk)
            with self.assertRaises(Conversation.DoesNotExist):
                self.remove(row, context=TenantContext.for_membership(member))
            self.client.force_authenticate(member.user)
            response = self.client.post(self.base + "participants/", {"membershipId": self.members[0].pk, "reason": "Denied"}, format="json")
            self.assertEqual(response.status_code, 404)
            actions = self.client.get(self.base).json()["conversation"]["access"]["actions"]
            self.assertNotIn("conversations.participants", actions)

    def test_manager_and_scoped_supervisor_can_manage(self):
        self.members[2].role = EmployeeRole.SUPERVISOR
        self.members[2].save(update_fields=["role"])
        context = TenantContext.for_membership(self.members[2])
        with self.assertRaises(Conversation.DoesNotExist):
            self.add(context=context)
        link = EmployeeGroupSupervision.objects.create(employee=self.members[2], group=self.group)
        row, created = self.add(context=context)
        self.assertTrue(created)
        self.remove(row, context=context)
        link.delete()
        for role in (EmployeeRole.OWNER, EmployeeRole.ADMIN):
            self.members[2].role = role
            self.members[2].save(update_fields=["role"])
            row, created = self.add(context=context)
            self.assertTrue(created)
            self.remove(row, context=context)

    def test_foreign_blocked_inactive_and_forged_actors_cannot_operate(self):
        with self.assertRaises(ValidationError):
            self.add(membership_id=self.foreign_member.pk)
        for changes in ({"blocked_at": timezone.now()}, {"blocked_at": None}):
            OrganizationMembership.objects.filter(pk=self.members[1].pk).update(**changes)
            if changes["blocked_at"] is None:
                self.members[1].user.is_active = False
                self.members[1].user.save(update_fields=["is_active"])
            with self.assertRaises(ValidationError):
                self.add()
        with self.assertRaises(Conversation.DoesNotExist):
            self.add(context=TenantContext.for_membership(self.foreign_member))
        with self.assertRaises(Conversation.DoesNotExist):
            self.add(context=replace(self.context, actor_user=self.members[2].user))
        OrganizationMembership.objects.filter(pk=self.members[0].pk).update(blocked_at=timezone.now())
        with self.assertRaises(Conversation.DoesNotExist):
            self.add(membership_id=self.members[2].pk)
        with self.assertRaises(Conversation.DoesNotExist):
            post_operator_message(context=self.context, conversation=self.conversation, text="Denied")

    def test_blocking_participant_revokes_http_and_direct_replies(self):
        self.add()
        context = TenantContext.for_membership(self.members[1])
        self.members[1].block()
        self.client.force_authenticate(self.members[1].user)
        self.assertIn(self.client.get(self.base + "messages/").status_code, {403, 404})
        self.assertIn(self.client.post(self.base + "messages/", {"text": "Denied"}, format="json").status_code, {403, 404})
        with self.assertRaises(Conversation.DoesNotExist):
            post_operator_message(context=context, conversation=self.conversation, text="Denied")

    def test_runtime_role_can_manage_and_reply_only_in_current_tenant(self):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            with tenant_atomic(self.context):
                row, _ = self.add()
                message = post_operator_message(
                    context=TenantContext.for_membership(self.members[1]),
                    conversation=self.conversation, text="Runtime answer",
                )
                self.assertEqual(message.author_user_id, self.members[1].user_id)
                with self.assertRaises(ValidationError):
                    self.add(membership_id=self.foreign_member.pk)
                self.remove(row)
                with self.assertRaises(Conversation.DoesNotExist):
                    post_operator_message(
                        context=TenantContext.for_membership(self.members[1]),
                        conversation=self.conversation, text="Revoked",
                    )

    def test_limit_idempotency_rejoin_and_protected_paginated_journal(self):
        self.organization.additional_participant_limit = 1
        self.organization.save(update_fields=["additional_participant_limit"])
        response = self.client.post(self.base + "participants/", {
            "membershipId": self.members[1].pk, "reason": "Internal consultation",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        row = self.conversation.participants.get(pk=response.json()["participant"]["id"])
        self.assertEqual(row.joined_by_id, self.members[0].pk)
        self.assertIsNotNone(row.joined_at)
        repeated, created = self.add(reason="Retry")
        self.assertFalse(created)
        self.assertEqual(repeated.pk, row.pk)
        self.assertEqual(repeated.join_reason, "Internal consultation")
        with self.assertRaises(ValidationError):
            self.add(membership_id=self.members[2].pk)
        responsible, _ = self.add(membership_id=self.members[0].pk)
        self.assertEqual(self.conversation.participants.additional().count(), 1)
        self.organization.additional_participant_limit = 0
        self.organization.save(update_fields=["additional_participant_limit"])
        self.assertEqual(self.add()[0].pk, row.pk)
        self.assertTrue(self.remove(row)[1])
        self.assertFalse(self.remove(row, reason="Retry")[1])
        row.refresh_from_db()
        self.assertEqual(row.left_by_id, self.members[0].pk)
        self.assertEqual(row.leave_reason, "Consultation finished")
        self.assertGreaterEqual(row.left_at, row.joined_at)
        with self.assertRaises(ValidationError):
            self.add()
        self.organization.additional_participant_limit = 1
        self.organization.save(update_fields=["additional_participant_limit"])
        rejoined, _ = self.add()
        self.assertNotEqual(rejoined.pk, row.pk)
        self.remove(row)
        self.assertIsNone(self.conversation.participants.get(pk=rejoined.pk).left_at)
        page = self.client.get(self.base + "participants/history/?pageSize=1&page=2").json()
        self.assertEqual(page["total"], 3)
        self.assertEqual(page["pageSize"], 1)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(self.client.patch(self.base + "participants/history/", {}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(self.base + f"participants/{responsible.pk}/", {"reason": "Finished"}, format="json").status_code, 200)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assigned_operator_id, self.members[0].user_id)

    def test_limit_api_is_management_only_and_preserves_existing_participants(self):
        row, _ = self.add()
        url = "/api/v1/conversations/participant-limit/"
        self.assertEqual(self.client.patch(url, {"additionalParticipantLimit": 0}, format="json").status_code, 403)
        self.members[2].role = EmployeeRole.ADMIN
        self.members[2].save(update_fields=["role"])
        self.client.force_authenticate(self.members[2].user)
        self.assertEqual(self.client.get(url).json()["additionalParticipantLimit"], 5)
        self.assertEqual(self.client.patch(url, {"additionalParticipantLimit": 0}, format="json").status_code, 200)
        self.assertIsNone(self.conversation.participants.get(pk=row.pk).left_at)
        self.assertEqual(self.client.patch(url, {"additionalParticipantLimit": -1}, format="json").status_code, 400)
