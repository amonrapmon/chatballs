"""Selected status time and durable block cuts in the real isolated test DB."""

from datetime import timedelta
from io import BytesIO
from uuid import uuid4

from django.db import DatabaseError, connection, transaction
from django.utils import timezone
from openpyxl import load_workbook

from chatballs.conversations.support_filters import ReportFilters
from chatballs.conversations.support_report import calculate_support_report
from chatballs.conversations.support_report_test_base import SupportReportTestBase
from chatballs.identity.group_models import EmployeeGroupMember
from chatballs.identity.models import HumanUser, OrganizationMembership
from chatballs.identity.supervision_models import EmployeeGroupSupervision
from chatballs.identity.work_status_models import WorkStatusOperation
from chatballs.identity.work_status_services import change_work_status
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import TenantAPIClient


class SupportWorkStatusTests(SupportReportTestBase):
    def setUp(self):
        self.colleague_user = HumanUser.objects.create(email="time@reports.test", full_name="=Unsafe")
        self.colleague = OrganizationMembership.objects.create(organization=self.organization,
                                                              user=self.colleague_user, role="EMPLOYEE")
        self.colleague_context = TenantContext.for_membership(self.colleague)
        self.first = self.change()
        self.start = self.first.changed_at
        self.end = timezone.now() + timedelta(hours=1)

    def change(self, status="READY", version=0):
        return change_work_status(context=self.colleague_context, status=status,
                                  expected_version=version, operation_id=uuid4())

    def report(self, *, context=None, **filters):
        return calculate_support_report(context=context or self.context, filters=ReportFilters(
            self.start, self.end, "Europe/Moscow", **filters,
        ))

    def test_block_cut_survives_unblock_and_noop_then_new_transition_resumes(self):
        second = self.change("BUSY", 1)
        self.colleague.block()
        self.first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNone(self.first.stopped_at)
        self.assertEqual(second.stopped_at, self.colleague.blocked_at)
        self.colleague.refresh_from_db()
        self.assertEqual(self.colleague.work_status, "BUSY")
        expected = round((second.stopped_at - second.changed_at).total_seconds(), 6)
        statuses = self.report(employee=self.colleague_user.pk)["employees"][0]["workStatuses"]
        self.assertTrue(statuses["complete"])
        self.assertEqual(statuses["values"]["BUSY"]["seconds"], expected)
        self.assertEqual(statuses["values"]["BUSY"]["currentIntervals"], 0)
        self.colleague.unblock()
        self.change("BUSY", 2)  # No-op does not resume a cut selection.
        repeated = self.report(employee=self.colleague_user.pk)
        self.assertEqual(repeated["workStatusTotals"]["values"]["BUSY"]["seconds"], expected)
        self.assertFalse(repeated["workStatusDetails"][-1]["current"])
        third = self.change("BREAK", 2)
        resumed = self.report(employee=self.colleague_user.pk)
        self.assertEqual(resumed["workStatusTotals"]["values"]["BUSY"]["seconds"], expected)
        self.assertEqual(resumed["workStatusDetails"][-1]["from"], third.changed_at.isoformat())
        self.assertEqual(resumed["workStatusTotals"]["values"]["BREAK"]["currentIntervals"], 1)

    def test_runtime_block_is_atomic_scoped_and_stop_cannot_be_forged(self):
        foreign = change_work_status(context=TenantContext.for_membership(self.foreign_member),
                                    status="READY", expected_version=0, operation_id=uuid4())
        with tenant_atomic(self.context):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            try:
                self.colleague.block()
                operation = WorkStatusOperation.objects.get(pk=self.first.pk)
                self.assertEqual(operation.stopped_at, self.colleague.blocked_at)
                self.assertFalse(WorkStatusOperation.objects.filter(pk=foreign.pk).exists())
                with self.assertRaises(DatabaseError), transaction.atomic():
                    WorkStatusOperation.objects.filter(pk=self.first.pk).update(stopped_at=None)
                self.assertFalse(self.report(employee=self.colleague_user.pk)["workStatusDetails"][-1]["current"])
            finally:
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL ROLE NONE")

    def test_supervisor_and_group_selection_exclude_outsider_time_and_details(self):
        EmployeeGroupMember.objects.create(organization=self.organization, group=self.group, employee=self.colleague)
        supervisor_user = HumanUser.objects.create(email="time-supervisor@reports.test")
        supervisor = OrganizationMembership.objects.create(organization=self.organization, user=supervisor_user, role="SUPERVISOR")
        control = EmployeeGroupSupervision.objects.create(organization=self.organization, employee=supervisor, group=self.group)
        report = self.report(context=TenantContext.for_membership(supervisor))
        self.assertEqual([row["employee"] for row in report["employees"]], [self.colleague_user.pk])
        self.assertEqual({row["employee"] for row in report["workStatusDetails"]}, {self.colleague_user.pk})
        self.assertTrue(report["workStatusTotals"]["complete"])
        member_link = self.colleague.group_links.get(group=self.group)
        member_link.delete()
        group_report = self.report(group=self.group.pk)
        row = next(item for item in group_report["employees"] if item["employee"] == self.colleague_user.pk)
        self.assertFalse(row["workStatuses"]["included"])
        self.assertIsNone(row["workStatuses"]["values"]["READY"]["seconds"])
        self.assertEqual(group_report["workStatusDetails"], [])
        control.delete()
        revoked = self.report(context=TenantContext.for_membership(supervisor))
        self.assertEqual(revoked["employees"], [])
        self.assertEqual(revoked["workStatusDetails"], [])

    def test_api_and_both_exports_contain_cuts_missing_values_and_no_formulas(self):
        self.colleague.block()
        client = TenantAPIClient()
        client.force_authenticate(self.user)
        base = f"/api/v1/organizations/{self.organization.public_id}/conversations/support-report"
        params = {"from": self.start.isoformat(), "to": self.end.isoformat(), "timezone": "Europe/Moscow",
                  "employee": self.colleague_user.pk}
        api = client.get(base + "/", params).json()
        expected = api["workStatusTotals"]["values"]["READY"]["seconds"]
        self.assertFalse(api["workStatusDetails"][0]["current"])
        csv = client.get(base + ".csv", params)
        self.assertEqual(csv.status_code, 200)
        self.assertIn(str(expected), csv.content.decode("utf-8-sig"))
        workbook = load_workbook(BytesIO(client.get(base + ".xlsx", params).content), data_only=False)
        self.assertEqual(len(workbook.worksheets), 5)
        metrics = list(workbook.worksheets[1].values)
        ready = next(row for row in metrics if row[0] == "totals" and row[3] == "workStatus.READY")
        self.assertEqual(ready[5], expected)
        for sheet in workbook:
            self.assertTrue(all(cell.data_type != "f" for row in sheet for cell in row))
        no_history = self.report(employee=self.user.pk)
        self.assertIsNone(no_history["workStatusTotals"]["values"]["UNAVAILABLE"]["seconds"])
