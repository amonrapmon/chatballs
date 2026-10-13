"""HTTP and service scopes use current roles and explicit supervision."""

from datetime import timedelta
from uuid import uuid4

from django.utils import timezone
from django.db import connection
from rest_framework.exceptions import NotFound, PermissionDenied

from chatballs.conversations.domain_events import record_fact
from chatballs.conversations.domain_event_models import ConversationEventHistoryStart
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import EmployeeRole, OrganizationMembership
from chatballs.identity.supervision_models import EmployeeGroupSupervision
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import TenantAPIClient

from .corrections import append_quality_correction
from .jobs import finish_quality_job, start_quality_job
from .models import QualityJob
from .selectors import job_for_context
from .test_base import CRITERIA, QualityTestBase


class QualityAPITests(QualityTestBase):
    @classmethod
    def setUpTestData(cls):
        ConversationEventHistoryStart.objects.get_or_create(pk=1)
        super().setUpTestData()

    def setUp(self):
        self.client = TenantAPIClient()
        self.client.force_authenticate(self.context.actor_user)
        self.root = f"/api/v1/organizations/{self.organization.public_id}/conversations/"
        self.group = EmployeeGroup.objects.create(organization=self.organization, name="Managed quality")
        self.conversation.group = self.group
        self.conversation.save(update_fields=["group"])
        self.supervisor = self.members[EmployeeRole.SUPERVISOR]
        self.link = EmployeeGroupSupervision.objects.create(
            organization=self.organization, group=self.group, employee=self.supervisor,
        )

    def analyzed_job(self):
        self.configure()
        message = self.message()
        completion = record_fact(self.conversation, "CLOSED", actor_kind="HUMAN",
                                 initiated_by_id=self.context.actor_user.pk, responsible_id=self.context.actor_user.pk)
        job = QualityJob.objects.get(completion_event_id=completion.operation_id)
        start_quality_job(context=self.context, job_id=job.pk)
        finish_quality_job(context=self.context, job_id=job.pk, validated_result={
            "conclusions": [{"code": "resolution", "value": 1, "explanation": "Explained",
                             "recommendations": ["Follow up"], "messageIds": [message.pk]}],
            "temporalFacts": {"state": "missing_history"},
        })
        return job, message

    def test_settings_and_launch_restrict_roles_and_reject_missing_completion(self):
        response = self.client.get(self.root + "quality/settings/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["enabled"])
        self.assertEqual(self.client.put(self.root + "quality/settings/",
                                        {"enabled": True}, format="json").status_code, 400)
        self.assertEqual(self.client.put(self.root + "quality/settings/", {
            "enabled": True, "criteria": CRITERIA}, format="json").status_code, 200)
        launch = self.root + f"{self.conversation.pk}/quality/launch/"
        response = self.client.post(launch, {"operationId": str(uuid4())}, format="json")
        self.assertEqual((response.status_code, response.data["errorCode"]), (400, "missing_history"))
        self.assertEqual(response.data["state"], "unavailable")
        completion = record_fact(self.conversation, "CLOSED")
        for role in (EmployeeRole.EMPLOYEE, EmployeeRole.SUPERVISOR):
            self.client.force_authenticate(self.members[role].user)
            self.assertEqual(self.client.get(self.root + "quality/settings/").status_code, 403)
            self.assertEqual(self.client.post(launch, {"operationId": str(uuid4())}, format="json").status_code, 403)
        self.client.force_authenticate(self.context.actor_user)
        operation = {"operationId": str(uuid4()), "repeat": True}
        first = self.client.post(launch, operation, format="json")
        second = self.client.post(launch, operation, format="json")
        self.assertEqual(first.status_code, 202, first.data)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(first.data["revision"], 2)
        self.assertEqual(first.data["completionEventId"], str(completion.operation_id))
        self.assertEqual(first.data["temporalFacts"]["state"], "available")

    def test_original_effective_evidence_recommendations_history_and_409(self):
        job, message = self.analyzed_job()
        self.client.force_authenticate(self.supervisor.user)
        url = self.root + f"quality/jobs/{job.pk}/"
        correction = {"expectedRevision": 0, "criterionCode": "resolution", "value": 2, "reason": "Reviewed"}
        response = self.client.post(url + "corrections/", correction, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        row = response.data["conclusions"][0]
        self.assertEqual((row["originalValue"], row["effectiveValue"]), (1, 2))
        self.assertEqual(row["recommendations"], ["Follow up"])
        self.assertEqual(response.data["corrections"][0]["author"]["membershipId"], self.supervisor.pk)
        self.assertEqual(response.data["corrections"][0]["reason"], "Reviewed")
        self.assertEqual(self.client.get(row["evidence"][0]["url"]).data["text"], message.text)
        self.assertEqual(self.client.post(url + "corrections/", correction, format="json").status_code, 409)
        job.result.refresh_from_db()
        self.assertEqual(job.result.data["conclusions"][0]["value"], 1)
        self.assertEqual(job.result.corrections.count(), 1)

    def test_direct_ids_links_filters_operator_and_revoked_supervision_cannot_leak(self):
        job, message = self.analyzed_job()
        url = self.root + f"quality/jobs/{job.pk}/"
        foreign = self.message(conversation=self.foreign_conversation)
        self.assertEqual(self.client.get(url + f"messages/{foreign.pk}/").status_code, 404)
        self.client.force_authenticate(self.supervisor.user)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.link.delete()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(url + f"messages/{message.pk}/").status_code, 404)
        self.client.force_authenticate(self.members[EmployeeRole.EMPLOYEE].user)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_authenticate(self.foreign_member.user)
        foreign_root = f"/api/v1/organizations/{self.foreign.public_id}/conversations/"
        self.assertEqual(self.client.get(foreign_root + f"quality/jobs/{job.pk}/").status_code, 404)
        self.client.force_authenticate(self.context.actor_user)
        params = {"from": (self.conversation.created_at - timedelta(seconds=1)).isoformat(),
                  "to": (timezone.now() + timedelta(seconds=1)).isoformat(), "timezone": "UTC"}
        response = self.client.get(self.root + "quality/report/", {**params, "group": self.group.pk})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row["id"] for row in response.data["jobs"]], [job.pk])
        self.assertEqual(response.data["jobs"][0]["criteria"], CRITERIA)
        self.assertEqual(response.data["jobs"][0]["criteriaVersion"], 1)
        for key, value in (("employee", self.foreign_member.user_id),
                           ("group", EmployeeGroup.objects.create(organization=self.foreign, name="Foreign").pk)):
            response = self.client.get(self.root + "quality/report/", {**params, key: value})
            self.assertEqual(response.status_code, 404)

    def test_runtime_scope_and_stale_context_recheck_current_access(self):
        job, message = self.analyzed_job()
        with tenant_atomic(self.foreign_context):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            with self.assertRaises(NotFound):
                job_for_context(self.foreign_context, job.pk)
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
        context = TenantContext.for_membership(self.supervisor)
        with tenant_atomic(context):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            self.assertEqual(job_for_context(context, job.pk).pk, job.pk)
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
        OrganizationMembership.objects.filter(pk=self.supervisor.pk).update(role=EmployeeRole.EMPLOYEE)
        with self.assertRaises(PermissionDenied):
            append_quality_correction(context=context, result_id=job.result.pk, expected_revision=0,
                                      criterion_code="resolution", value=2, reason="Stale authorization")
        OrganizationMembership.objects.filter(pk=self.context.membership_id).update(blocked_at=timezone.now())
        with self.assertRaises(PermissionDenied):
            self.configure()

    def test_criteria_changes_and_historical_filters_keep_original_scale(self):
        job, _ = self.analyzed_job()
        self.configure(criteria=[{"code": "resolution", "description": "New scale", "scale": ["good", "bad"]}])
        params = {"from": self.conversation.created_at.isoformat(),
                  "to": (timezone.now() + timedelta(seconds=1)).isoformat(), "timezone": "UTC",
                  "group": self.group.pk, "employee": self.context.actor_user.pk}
        self.conversation.group = None
        self.conversation.save(update_fields=["group"])
        response = self.client.get(self.root + "quality/report/", params)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["jobs"][0]["criteria"], CRITERIA)
        self.assertEqual(response.data["jobs"][0]["criteriaVersion"], 1)
