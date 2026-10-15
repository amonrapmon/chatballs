import copy
import json
import uuid

from django.conf import settings
from django.db import connection
from django.middleware.csrf import _get_new_csrf_string
from django.test import TransactionTestCase

from chatballs.ai.skill_templates.engine import render_template
from chatballs.ai.skill_templates.order_basis import order_basis
from chatballs.ai.skills_models import AgentSkill, Skill, SkillRequest
from chatballs.ai.skills_test_support import SkillsSetup
from chatballs.conversations.models import Message
from chatballs.identity.models import AuditEvent, EmployeeRole
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import TenantAPIClient


class SkillTemplatesAPITests(SkillsSetup, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.basis = order_basis(language="ru")

    def preview(self, config=None, data=None, url=None):
        template = self.basis["templates"][0]
        return self.client.post(url or self.url + "preview/", {
            "configuration": config or self.basis, "templateId": template["id"],
            "data": template["examples"][0] if data is None else data,
        }, format="json")

    def test_real_session_csrf_body_is_bounded_before_authentication_parses_it(self):
        client = TenantAPIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        csrf = _get_new_csrf_string()
        client.cookies[settings.CSRF_COOKIE_NAME] = csrf
        template = self.basis["templates"][0]
        body = {"configuration": self.basis, "templateId": template["id"], "data": template["examples"][0]}
        response = client.post(self.url + "preview/", body, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(client.post(self.url + "preview/", body, format="json").status_code, 403)
        exact = json.dumps({"configuration": self.basis})
        exact += " " * (160_000 - len(exact.encode("utf-8")))
        for payload, status in ((exact, 200), (exact + " ", 413)):
            response = client.post(self.url + "validate/", payload, content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
            self.assertEqual(response.status_code, status, response.content)
        body["data"] = {"huge": "x" * 160_000}
        response = client.post(self.url + "preview/", body, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 413)

    def test_opt_in_basis_preview_and_validate_are_read_only_and_match_runtime(self):
        basis = self.client.get(self.url + "bases/orders/")
        self.assertEqual(basis.status_code, 200, basis.content)
        self.assertEqual(basis.json()["configuration"], self.basis)
        for language in ("en", "ru"):
            self.organization.language = language
            self.organization.save(update_fields=["language"])
            config = self.client.get(self.url + "bases/orders/").json()["configuration"]
            self.assertEqual(config, order_basis(language=language))
        response = self.preview()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), render_template(
            self.basis["templates"][0], self.basis["templates"][0]["examples"][0], language="ru",
        ))
        valid = self.client.post(self.url + "validate/", {"configuration": self.basis}, format="json")
        self.assertEqual(valid.status_code, 200, valid.content)
        self.assertFalse(Skill.objects.exists())
        self.assertFalse(AgentSkill.objects.exists())
        self.assertFalse(SkillRequest.objects.exists())
        self.assertFalse(Message.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action__startswith="ai.skill_").exists())

    def test_atomic_save_stable_ids_retries_conflicts_and_independent_copies(self):
        key = str(uuid.uuid4())
        body = {"requestId": key, "configuration": self.basis}
        response = self.client.post(self.url, body, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        saved = response.json()["skill"]
        self.assertEqual(saved["templates"], self.basis["templates"])
        self.assertEqual(self.client.post(self.url, body, format="json").status_code, 200)
        self.assertEqual(Skill.objects.count(), 1)
        self.assertFalse(AgentSkill.objects.exists())
        draft = copy.deepcopy(self.basis)
        draft["templates"][0]["text"] += " changed"
        request = {"requestId": str(uuid.uuid4()), "expectedRevision": 1, "configuration": draft}
        updated = self.client.put(self.detail(saved), request, format="json")
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.json()["skill"]["templates"][0]["id"], saved["templates"][0]["id"])
        self.assertEqual(updated.json()["skill"]["revision"], 2)
        request["requestId"] = str(uuid.uuid4())
        self.assertEqual(self.client.put(self.detail(saved), request, format="json").status_code, 409)
        self.client.get(self.url + "bases/orders/")
        self.assertEqual(self.client.get(self.detail(saved)).json()["skill"], updated.json()["skill"])
        invalid = copy.deepcopy(draft)
        invalid["templates"][1]["html"] = "<script>DO-NOT-ECHO</script>"
        failed = self.client.put(self.detail(saved), {
            "requestId": str(uuid.uuid4()), "expectedRevision": 2,
            "configuration": {**invalid, "name": "Not saved"},
        }, format="json")
        self.assertEqual(failed.status_code, 400, failed.content)
        self.assertNotIn("DO-NOT-ECHO", str(failed.json()))
        self.assertEqual(self.client.get(self.detail(saved)).json()["skill"], updated.json()["skill"])
        self.assertEqual(SkillRequest.objects.count(), 2)

    def test_example_error_is_distinct_from_configuration_and_draft_survives(self):
        response = self.preview(data={"order_no": "4512"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["origin"], "example")
        draft = copy.deepcopy(self.basis)
        draft["templates"][0]["text"] = "First\n{{unknown}}"
        response = self.preview(config=draft)
        self.assertEqual(response.status_code, 400)
        error = response.json()["errors"][0]
        self.assertEqual((error["origin"], error["tab"], error["line"], error["column"]), ("configuration", "text", "2", "1"))
        self.assertEqual(error["path"], "templates[0]")
        self.basis["templates"][0]["examples"] = [{}]
        self.create_skill(**self.basis)

    def test_duplicate_json_keys_nonfinite_and_deep_input_are_rejected(self):
        for body in (
            '{"configuration":{"name":"a","name":"b"}}',
            '{"configuration":{"schema":{"properties":{"a":1,"a":2}}}}',
            '{"data":NaN}', '{"data":' + "[" * 1100 + "0" + "]" * 1100 + '}',
        ):
            response = self.client.post(self.url + "validate/", body, content_type="application/json")
            self.assertEqual(response.status_code, 400, response.content)
            self.assertEqual(response.json()["code"], "invalid_request")

    def test_manager_rights_foreign_preview_and_templates_inherit_rls(self):
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE chatballs_runtime_app")
        try:
            saved = self.create_skill(**self.basis)
            self.assertEqual(self.preview(url=self.detail(saved) + "preview/").status_code, 200)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
        for role in (EmployeeRole.EMPLOYEE, EmployeeRole.SUPERVISOR):
            self.membership.role = role
            self.membership.save(update_fields=["role"])
            for route in ("preview/", "validate/", "bases/orders/"):
                response = self.client.get(self.url + route) if route.startswith("bases") else self.preview(url=self.url + route)
                self.assertEqual(response.status_code, 403, response.content)
        self.membership.role = EmployeeRole.ADMIN
        self.membership.save(update_fields=["role"])
        self.assertEqual(self.preview().status_code, 200)
        foreign = Skill.objects.create(organization=self.other, name="Foreign", description="x", instruction="x", templates=self.basis["templates"])
        self.assertEqual(self.preview(url=f"{self.url}{foreign.public_id}/preview/").status_code, 404)
        for organization, expected in ((self.organization, 1), (self.other, 0)):
            with tenant_atomic(organization.pk):
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
                rows = list(Skill.objects.filter(public_id=saved["id"]).values_list("templates", flat=True))
                self.assertEqual(len(rows), expected)
                if rows:
                    self.assertEqual(rows[0], self.basis["templates"])
