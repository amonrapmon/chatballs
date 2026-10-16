"""Team HTTP, service and export boundaries on the real PostgreSQL test DB."""

from datetime import timedelta
from io import BytesIO

from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.exceptions import PermissionDenied

from chatballs.conversations.domain_events import record_fact
from chatballs.conversations.models import Conversation
from chatballs.conversations.selectors import visible_conversations_for
from chatballs.conversations.support_filters import ReportFilters
from chatballs.conversations.support_report import calculate_support_report
from chatballs.conversations.support_report_test_base import SupportReportTestBase
from chatballs.identity.group_models import EmployeeGroup, EmployeeGroupMember
from chatballs.identity.models import HumanUser, OrganizationMembership
from chatballs.identity.supervision_models import EmployeeGroupSupervision
from chatballs.identity.work_status_services import change_work_status
from chatballs.tenancy.context import TenantContext
from chatballs.testing import TenantAPIClient


class TeamResultScopeTests(SupportReportTestBase):
    def setUp(self):
        self.other_group = EmployeeGroup.objects.create(organization=self.organization, name="Other team")
        self.supervisor = OrganizationMembership.objects.create(
            organization=self.organization, role="SUPERVISOR",
            user=HumanUser.objects.create_user(email="team-manager@reports.test"),
        )
        self.outsider = OrganizationMembership.objects.create(
            organization=self.organization, role="EMPLOYEE",
            user=HumanUser.objects.create_user(email="hidden-worker@reports.test", full_name="Hidden worker"),
        )
        self.link = EmployeeGroupSupervision.objects.create(
            organization=self.organization, employee=self.supervisor, group=self.group,
        )
        self.staff_link = EmployeeGroupMember.objects.create(
            organization=self.organization, employee=self.member, group=self.group,
        )
        EmployeeGroupMember.objects.create(
            organization=self.organization, employee=self.outsider, group=self.other_group,
        )
        EmployeeGroupMember.objects.create(
            organization=self.organization, employee=self.supervisor, group=self.other_group,
        )
        self.outside = Conversation.objects.create(
            organization=self.organization, channel=self.conversation.channel, group=self.other_group,
            contact=self.conversation.contact, assigned_operator=self.outsider.user,
            control_mode="PAUSED", expected_responder="OPERATOR",
        )
        self.ungrouped = Conversation.objects.create(
            organization=self.organization, channel=self.conversation.channel,
            contact=self.conversation.contact, assigned_operator=self.supervisor.user,
            control_mode="PAUSED", expected_responder="OPERATOR",
        )
        self.conversation.expected_responder = "OPERATOR"
        self.conversation.save(update_fields=["expected_responder"])
        for conversation in (self.conversation, self.outside, self.ungrouped, self.foreign_conversation):
            record_fact(conversation, "ACCEPTED", actor_kind="HUMAN",
                        responsible_id=conversation.assigned_operator_id)
        self.context = TenantContext.for_membership(self.supervisor)
        self.filters = ReportFilters(self.conversation.created_at, timezone.now() + timedelta(hours=1), "UTC")
        self.params = {key: value for key, value in self.filters.payload().items() if value is not None}
        self.root = f"/api/v1/organizations/{self.organization.public_id}/conversations/"
        self.client = TenantAPIClient()
        self.client.force_authenticate(self.supervisor.user)

    def report(self):
        return calculate_support_report(context=self.context, filters=self.filters)

    def test_totals_time_details_and_exports_include_only_controlled_team(self):
        from uuid import uuid4

        for member in (self.member, self.outsider):
            change_work_status(context=TenantContext.for_membership(member), status="READY",
                               expected_version=0, operation_id=uuid4())
        response = self.client.get(self.root + "support-report/", self.params)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        report = response.data
        self.assertEqual(report["totals"]["observedCounts"]["accepted"], 1)
        self.assertEqual(report["currentLoad"], 1)
        self.assertEqual([row["employee"] for row in report["employees"]], [self.user.pk])
        self.assertEqual(report["workStatusTotals"]["employees"], 1)
        self.assertEqual({row["employee"] for row in report["workStatusDetails"]}, {self.user.pk})
        self.assertEqual({row["conversationId"] for row in report["details"]}, {self.conversation.pk})
        for extension in ("csv", "xlsx"):
            response = self.client.get(self.root + f"support-report.{extension}", self.params)
            self.assertEqual(response.status_code, 200)
            if extension == "csv":
                self.assertNotIn("Hidden worker", response.content.decode("utf-8-sig"))
            else:
                book = load_workbook(BytesIO(response.content))
                self.assertNotIn("Hidden worker", [cell for sheet in book for row in sheet.values for cell in row])
                # Export detail rows carry the same conversation/employee IDs as JSON.
                self.assertEqual({row[0] for row in list(book.worksheets[2].values)[1:]}, {self.conversation.pk})
                self.assertEqual({row[0] for row in list(book.worksheets[4].values)[1:]}, {self.user.pk})
        for key, value in (("employee", self.outsider.user_id), ("group", self.other_group.pk),
                           ("employee", self.foreign_user.pk), ("group", self.foreign_group.pk)):
            for suffix in ("/", ".csv", ".xlsx"):
                response = self.client.get(self.root + "support-report" + suffix, {**self.params, key: value})
                self.assertEqual(response.status_code, 404)

    def test_overview_is_managed_but_working_queue_and_dialogue_access_survive_revocation(self):
        http = self.client.get(self.root + "stats/")
        self.assertEqual(http["Cache-Control"], "private, no-store")
        response = http.data
        self.assertEqual(response["ops"]["openDialogs"], 1)
        self.assertEqual(response["period"]["dialogs"], 1)
        self.assertEqual(sum(response["chart"]["values"]), 1)
        self.assertEqual([row["conversationId"] for row in response["problems"]], [self.conversation.pk])
        self.assertEqual(response["waiting"], 2)
        self.link.delete()
        report = self.report()  # Cached context must not retain the removed grant.
        self.assertEqual(report["currentLoad"], 0)
        self.assertEqual(report["employees"], [])
        self.assertEqual(report["details"], [])
        self.assertEqual(report["workStatusTotals"]["employees"], 0)
        response = self.client.get(self.root + "stats/").data
        self.assertEqual(response["ops"]["openDialogs"], 0)
        self.assertEqual(response["period"]["dialogs"], 0)
        self.assertEqual(response["problems"], [])
        self.assertEqual(response["waiting"], 2)
        for conversation in (self.outside, self.ungrouped):
            self.assertEqual(self.client.get(self.root + f"{conversation.pk}/").status_code, 200)
        self.assertEqual(self.client.get(self.root + f"{self.conversation.pk}/").status_code, 404)
        for suffix in ("/", ".csv", ".xlsx"):
            self.assertEqual(self.client.get(self.root + "support-report" + suffix, self.params).status_code, 200)

    def test_removing_staff_membership_and_changing_role_are_effective_next_operation(self):
        self.staff_link.delete()
        report = self.report()
        self.assertEqual(report["employees"], [])
        self.assertEqual(report["totals"]["observedCounts"]["accepted"], 1)
        self.assertTrue(all(row["employee"] is None for row in report["details"]))
        self.assertEqual(report["workStatusDetails"], [])
        OrganizationMembership.objects.filter(pk=self.supervisor.pk).update(role="EMPLOYEE")
        with self.assertRaises(PermissionDenied):
            self.report()
        self.assertTrue(visible_conversations_for(self.context).filter(pk=self.outside.pk).exists())
        OrganizationMembership.objects.filter(pk=self.supervisor.pk).update(blocked_at=timezone.now())
        with self.assertRaises(PermissionDenied):
            self.report()

    def test_switching_control_changes_team_history_without_cancelling_own_work(self):
        employee_root = f"/api/v1/organizations/{self.organization.public_id}/employees/"
        target = employee_root + f"{self.user.pk}/work-status/history/"
        self.assertEqual(self.client.get(target).status_code, 200)
        self.assertEqual(self.client.get(employee_root + f"{self.outsider.user_id}/work-status/history/").status_code, 404)
        self.link.delete()
        EmployeeGroupSupervision.objects.create(
            organization=self.organization, employee=self.supervisor, group=self.other_group,
        )
        report = self.report()
        self.assertEqual([row["employee"] for row in report["employees"]], [self.supervisor.user_id, self.outsider.user_id])
        self.assertEqual({row["conversationId"] for row in report["details"]}, {self.outside.pk})
        self.assertEqual(self.client.get(target).status_code, 404)
        self.assertEqual(self.client.get(employee_root + f"{self.outsider.user_id}/work-status/history/").status_code, 200)
        self.assertEqual(self.client.get(employee_root + "me/work-status/history/").status_code, 200)
        self.assertEqual(self.client.get(self.root + f"{self.ungrouped.pk}/").status_code, 200)
