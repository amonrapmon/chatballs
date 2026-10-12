"""HTTP authorization and durable availability in Django's test database."""

from uuid import uuid4

from django.db import connection, transaction
from django.utils import timezone

from chatballs import presence
from chatballs.identity.models import EmployeeRole, HumanUser, OrganizationMembership
from chatballs.identity.work_status_codes import WorkStatus
from chatballs.identity.work_status_models import WorkStatusOperation
from chatballs.identity.work_status_testing import WorkStatusTestBase
from chatballs.tenancy.context import TenantContext
from chatballs.testing import TenantAPIClient


class WorkStatusAPITests(WorkStatusTestBase):
    def setUp(self):
        super().setUp()
        self.client = TenantAPIClient()
        self.client.force_authenticate(self.user)
        colleague = HumanUser.objects.create(email="colleague@status.test")
        self.colleague = OrganizationMembership.objects.create(
            organization=self.organization, user=colleague, role=EmployeeRole.ADMIN,
        )
        self.base = f"/api/v1/organizations/{self.organization.public_id}/employees/"
        self.own_url = self.base + "me/work-status/"

    def post(self, **changes):
        return self.client.post(self.own_url, {
            "status": WorkStatus.READY, "expectedVersion": 0,
            "operationId": str(uuid4()), **changes,
        }, format="json")

    def test_initial_transition_replay_noop_and_version_conflict(self):
        self.assertEqual(self.client.get(self.own_url).json(), {
            "status": WorkStatus.UNAVAILABLE, "version": 0, "changedAt": None,
        })
        key = str(uuid4())
        response = self.post(operationId=key)
        self.assertEqual(response.status_code, 200)
        original = response.json()
        self.assertEqual((original["status"], original["version"], original["changed"]), (WorkStatus.READY, 1, True))
        self.assertIsNotNone(original["changedAt"])
        self.assertEqual(self.post().status_code, 409)
        noop = self.post(expectedVersion=1)
        self.assertFalse(noop.json()["changed"])
        self.assertEqual(self.post(status=WorkStatus.BUSY, expectedVersion=1).status_code, 200)
        self.assertEqual(self.post(operationId=key).json(), original)
        history = self.client.get(self.own_url + "history/?pageSize=1").json()
        self.assertEqual((history["total"], history["pageCount"]), (2, 2))
        self.assertEqual(history["items"][0]["status"], WorkStatus.BUSY)
        second = self.client.get(self.own_url + "history/?pageSize=1&page=2").json()
        self.assertEqual(second["items"], [original])

    def test_cannot_change_colleague_even_as_admin_or_inject_target(self):
        for actor in (self.user, self.colleague.user):
            self.client.force_authenticate(actor)
            response = self.client.post(self.base + f"{self.colleague.user_id}/work-status/", {
                "status": WorkStatus.BREAK, "expectedVersion": 0, "operationId": str(uuid4()),
            }, format="json")
            self.assertEqual(response.status_code, 405)
            self.assertEqual(self.post(userId=self.colleague.user_id).status_code, 400)
        self.assertFalse(WorkStatusOperation.objects.exists())

    def test_history_and_status_reads_follow_organization_and_management_rights(self):
        self.change()
        foreign_operation = self.change(status=WorkStatus.BREAK, context=TenantContext.for_membership(self.other))
        for suffix in ("", "history/"):
            self.assertEqual(self.client.get(self.base + f"{self.colleague.user_id}/work-status/" + suffix).status_code, 403)
        self.client.force_authenticate(self.colleague.user)
        for role in (EmployeeRole.ADMIN, EmployeeRole.OWNER):
            OrganizationMembership.objects.filter(pk=self.colleague.pk).update(role=role)
            target = self.base + f"{self.user.pk}/work-status/"
            self.assertEqual(self.client.get(target).json()["status"], WorkStatus.READY)
            items = self.client.get(target + "history/").json()["items"]
            self.assertEqual(len(items), 1)
            self.assertNotEqual(items[0]["operationId"], str(foreign_operation.operation_id))
        foreign_url = self.own_url.replace(str(self.organization.public_id), str(self.foreign.public_id))
        self.assertEqual(self.client.get(foreign_url).status_code, 404)
        self.assertEqual(self.client.post(foreign_url, {}, format="json").status_code, 404)
        foreign_user = HumanUser.objects.create(email="foreign-history@status.test")
        OrganizationMembership.objects.create(organization=self.foreign, user=foreign_user)
        for suffix in ("", "history/"):
            self.assertEqual(self.client.get(self.base + f"{foreign_user.pk}/work-status/" + suffix).status_code, 404)

    def test_blocked_and_inactive_actor_cannot_transition(self):
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(blocked_at=timezone.now())
        self.assertEqual(self.post().status_code, 404)
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(blocked_at=None)
        HumanUser.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.post().status_code, 404)
        self.assertFalse(WorkStatusOperation.objects.exists())

    def test_invalid_payloads_never_write(self):
        for changes in (
            {"status": "ONLINE"}, {"expectedVersion": True}, {"expectedVersion": "0"},
            {"expectedVersion": -1}, {"operationId": "bad"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.post(**changes).status_code, 400)
        for data in ({}, [], {"status": WorkStatus.READY}):
            self.assertEqual(self.client.post(self.own_url, data, format="json").status_code, 400)
        self.assertFalse(WorkStatusOperation.objects.exists())

    def test_directory_has_separate_status_time_presence_and_load(self):
        presence.touch(self.organization.pk, self.user.pk)
        operation = self.change(WorkStatus.BREAK)
        self.change(WorkStatus.READY, context=TenantContext.for_membership(self.other))
        foreign_user = HumanUser.objects.create(email="foreign-only@status.test")
        OrganizationMembership.objects.create(organization=self.foreign, user=foreign_user)
        blocked = HumanUser.objects.create(email="blocked@status.test")
        OrganizationMembership.objects.create(organization=self.organization, user=blocked, blocked_at=timezone.now())
        inactive = HumanUser.objects.create(email="inactive@status.test", is_active=False)
        OrganizationMembership.objects.create(organization=self.organization, user=inactive)
        url = f"/api/v1/organizations/{self.organization.public_id}/conversations/directory/"
        payload = self.client.get(url).json()
        rows = {row["id"]: row for row in payload["employees"]}
        self.assertEqual(set(rows), {self.user.pk, self.colleague.user_id})
        row = rows[self.user.pk]
        self.assertEqual(row["workStatus"], {"status": WorkStatus.BREAK, "version": 1, "changedAt": operation.changed_at.isoformat()})
        self.assertTrue(row["online"])
        self.assertIsNotNone(row["lastSeenAt"])
        self.assertEqual(row["openDialogs"], 0)
        self.assertFalse(rows[self.colleague.user_id]["online"])
        self.assertIsNone(rows[self.colleague.user_id]["workStatus"]["changedAt"])

    def test_runtime_app_role_can_use_api_and_sees_only_current_tenant(self):
        self.change(WorkStatus.BREAK, context=TenantContext.for_membership(self.other))
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            response = self.post()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.client.get(self.own_url).json()["status"], WorkStatus.READY)
            history = self.client.get(self.own_url + "history/").json()["items"]
            self.assertEqual([row["status"] for row in history], [WorkStatus.READY])

    def test_status_does_not_reassign_or_change_conversation_visibility(self):
        from chatballs.channels.models import Channel
        from chatballs.conversations.models import Contact, ControlMode, Conversation
        from chatballs.conversations.selectors import conversation_is_visible
        from chatballs.identity.group_models import EmployeeGroup

        channel = Channel.objects.create(organization=self.organization, code="work", name="Work")
        contact = Contact.objects.create(organization=self.organization, name="Contact")
        group = EmployeeGroup.objects.create(organization=self.organization, name="Hidden")
        assigned = Conversation.objects.create(
            organization=self.organization, channel=channel, contact=contact,
            group=group, assigned_operator=self.user, control_mode=ControlMode.HUMAN,
        )
        hidden = Conversation.objects.create(
            organization=self.organization, channel=channel, contact=contact, group=group,
        )
        self.assertEqual(self.post(status=WorkStatus.UNAVAILABLE).status_code, 200)
        self.assertEqual(self.post(status=WorkStatus.BREAK).status_code, 200)
        assigned.refresh_from_db()
        self.assertEqual(assigned.assigned_operator_id, self.user.pk)
        self.assertEqual(assigned.control_mode, ControlMode.HUMAN)
        self.assertTrue(conversation_is_visible(actor=self.membership, conversation=assigned))
        self.assertFalse(conversation_is_visible(actor=self.membership, conversation=hidden))
