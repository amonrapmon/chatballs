from copy import deepcopy

from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from chatballs.identity.models import EmployeeRole
from chatballs.tenancy.context import TenantContext

from .jobs import finish_quality_job, start_quality_job
from .presentation import job_payload
from .test_base import CRITERIA, QualityTestBase
from .views import QualityCorrectionView, QualitySettingsView


class QualityUIContractTests(QualityTestBase):
    def test_browser_selection_preserves_numeric_types_and_original_result(self):
        self.configure(criteria=[{**CRITERIA[0], "scale": [1, 1.0]}])
        job = self.job()
        start_quality_job(context=self.context, job_id=job.pk)
        finish_quality_job(context=self.context, job_id=job.pk, validated_result={"conclusions": [
            {"code": "resolution", "value": 1, "explanation": "Explained", "recommendations": [], "messageIds": []},
        ]})
        literals = self.settings_response().data["criteriaValueLiterals"]
        self.assertEqual(literals["resolution"], ["1", "1.0"])

        def correct(data):
            request = APIRequestFactory().post("/", data, format="json")
            request.tenant_context = self.context
            force_authenticate(request, user=self.context.actor_user)
            return QualityCorrectionView.as_view()(request, job_id=job.pk)

        body = {"expectedRevision": 0, "criterionCode": "resolution", "scaleIndex": 1, "reason": "Reviewed"}
        response = correct(body)
        self.assertEqual(response.status_code, 200)
        conclusion = response.data["conclusions"][0]
        self.assertEqual(conclusion["effectiveScaleIndex"], 1)
        self.assertIs(type(conclusion["effectiveValue"]), float)
        self.assertIs(type(conclusion["originalValue"]), int)
        self.assertEqual(correct(body).status_code, 409)
        self.assertEqual(correct({**body, "expectedRevision": 1, "value": 1}).status_code, 400)
        for index in (-1, True, 2, "1"):
            self.assertEqual(correct({**body, "expectedRevision": 1, "scaleIndex": index}).status_code, 400)

    def settings_response(self, role=EmployeeRole.OWNER):
        member = self.members[role]
        request = APIRequestFactory().get("/")
        request.tenant_context = TenantContext.for_membership(member)
        force_authenticate(request, user=member.user)
        return QualitySettingsView.as_view()(request)

    def test_named_versions_preserve_historical_job_and_required_fields(self):
        original = [{**CRITERIA[0], "name": "Решение вопроса"}]
        self.configure(criteria=original)
        job = self.job()
        changed = deepcopy(original)
        changed[0].update(name="Новое название", scale=["Да", "Нет"])
        self.configure(criteria=changed)
        response = self.settings_response()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["criteriaVersion"], 2)
        self.assertEqual(response.data["nextCriteriaVersion"], 3)
        self.assertTrue(response.data["criteriaCreatedAt"])
        self.assertEqual(job_payload(job, self.context)["criteria"], original)
        self.assertEqual(job_payload(job, self.context)["criteriaVersion"], 1)
        for name in ("", " ", 123, "x" * 201):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.configure(criteria=[{**original[0], "name": name}])

    def test_editor_catalog_and_independent_toggle_do_not_revise_criteria(self):
        settings = self.configure(enabled=False)
        version_id = settings.current_version_id
        self.configure(criteria=None, enabled=True)
        response = self.settings_response()
        self.assertEqual(response.data["criteriaVersion"], 1)
        self.assertEqual(settings.current_version_id, version_id)
        catalog = response.data["scales"]
        self.assertEqual([row["id"] for row in catalog], ["yes_no", "one_five", "zero_ten"])
        self.assertEqual(catalog[1]["values"], list(range(1, 6)))
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(self.settings_response(EmployeeRole.EMPLOYEE).status_code, 403)
        self.assertEqual(self.settings_response(EmployeeRole.SUPERVISOR).status_code, 403)
