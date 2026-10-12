from uuid import uuid4

from django.db import DatabaseError, connection, transaction

from chatballs.conversations.assignment_policy import AssignmentPolicy, STATUS_FIELDS
from chatballs.conversations.transfer_operation_test_base import TransferOperationTestBase
from chatballs.conversations.transfer_test_base import TransferTestBase
from chatballs.identity.models import EmployeeRole, Organization
from chatballs.identity.work_status_services import change_work_status
from chatballs.presence import touch
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


class AssignmentPolicyTests(TransferTestBase):
    def setUp(self):
        super().setUp()
        self.root = f"/api/v1/organizations/{self.organization.public_id}/conversations/"
        self.url = self.root + "assignment-policy/"
        self.data = {status: status == "READY" for status in STATUS_FIELDS}

    def test_policy_is_explicit_complete_boolean_and_admin_only(self):
        self.assertEqual(self.client.get(self.url).data["allowedStatuses"],
                         {status: True for status in STATUS_FIELDS})
        for data in ({"READY": True}, {**self.data, "EXTRA": False}, {**self.data, "BUSY": 1}):
            self.assertEqual(self.client.put(self.url, data, format="json").status_code, 400)
        self.assertTrue(all(self.client.get(self.url).data["allowedStatuses"].values()))
        response = self.client.put(self.url, self.data, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["allowedStatuses"], self.data)
        self.client.force_authenticate(self.members[EmployeeRole.SUPERVISOR].user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.put(self.url, self.data, format="json").status_code, 403)
        self.client.force_authenticate(self.members[EmployeeRole.ADMIN].user)
        self.assertEqual(self.client.put(self.url, self.data, format="json").status_code, 200)

    def test_unconfigured_policy_rejects_assignment(self):
        AssignmentPolicy.objects.filter(organization=self.organization).delete()
        data = {"userId": self.members[EmployeeRole.EMPLOYEE].user_id}
        response = self.client.post(f"{self.root}{self.conversation.pk}/assignee/", data, format="json")
        self.assertEqual(response.status_code, 400)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assignment_version, 0)

    def test_policy_rls_denies_missing_and_foreign_tenant(self):
        self.client.put(self.url, self.data, format="json")
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            self.assertFalse(AssignmentPolicy.objects.exists())
        with tenant_atomic(self.context):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            self.assertEqual(AssignmentPolicy.objects.count(), 1)
            with self.assertRaises(DatabaseError), transaction.atomic():
                AssignmentPolicy.objects.create(
                    organization=self.foreign, ready=True, busy=True,
                    break_allowed=True, unavailable=True,
                )
        foreign_url = f"/api/v1/organizations/{self.foreign.public_id}/conversations/assignment-policy/"
        self.assertIn(self.client.get(foreign_url).status_code, (403, 404))

    def test_initial_policy_allows_every_status_and_is_not_reset_by_organization_updates(self):
        for status in STATUS_FIELDS:
            member = self.members[EmployeeRole.EMPLOYEE]
            member.refresh_from_db()
            change_work_status(context=TenantContext.for_membership(member), status=status,
                               expected_version=member.work_status_version, operation_id=uuid4())
            response = self.client.post(f"{self.root}{self.conversation.pk}/assignee/",
                                       {"userId": member.user_id}, format="json")
            self.assertEqual(response.status_code, 200)
        self.client.put(self.url, self.data, format="json")
        self.organization.name = "Renamed"
        self.organization.save(update_fields=["name"])
        self.assertEqual(self.client.get(self.url).data["allowedStatuses"], self.data)

    def test_platform_creation_initializes_tenant_policy_without_granting_platform_read(self):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_platform")
            organization = Organization.objects.create(name="New", slug="new-policy")
            with self.assertRaises(DatabaseError), transaction.atomic():
                AssignmentPolicy.objects.filter(organization=organization).get()
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE NONE")
            with tenant_atomic(organization.pk):
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
                policy = AssignmentPolicy.objects.get(organization=organization)
                self.assertTrue(all(getattr(policy, field) for field in STATUS_FIELDS.values()))


class AssignmentAvailabilityTests(TransferOperationTestBase):
    def test_each_status_is_checked_independently_of_presence(self):
        member = self.members[EmployeeRole.EMPLOYEE]
        context = TenantContext.for_membership(member)
        touch(self.organization.pk, member.user_id)
        for status, field in STATUS_FIELDS.items():
            member.refresh_from_db()
            change_work_status(context=context, status=status,
                               expected_version=member.work_status_version, operation_id=uuid4())
            with transaction.atomic():
                setattr(self.policy, field, False)
                self.policy.save(update_fields=[field])
                self.assertEqual(self.post().status_code, 400)
                setattr(self.policy, field, True)
                self.policy.save(update_fields=[field])
                self.assertEqual(self.post().status_code, 200)
                transaction.set_rollback(True)

    def test_directory_separates_status_presence_load_and_filters_foreign_members(self):
        member = self.members[EmployeeRole.EMPLOYEE]
        change_work_status(context=TenantContext.for_membership(member), status="READY",
                           expected_version=0, operation_id=uuid4())
        response = self.client.get(self.root + "directory/")
        self.assertEqual(response.status_code, 200)
        rows = {row["id"]: row for row in response.data["employees"]}
        self.assertNotIn(self.foreign_user.pk, rows)
        row = rows[member.user_id]
        self.assertEqual(row["workStatus"]["status"], "READY")
        self.assertFalse(row["online"])
        self.assertIsNone(row["lastSeenAt"])
        self.assertTrue(row["assignmentAllowed"])
        self.assertEqual(row["openDialogs"], 0)
        self.assertEqual(self.post().status_code, 200)
        rows = {row["id"]: row for row in self.client.get(self.root + "directory/").data["employees"]}
        self.assertEqual(rows[member.user_id]["openDialogs"], 1)
