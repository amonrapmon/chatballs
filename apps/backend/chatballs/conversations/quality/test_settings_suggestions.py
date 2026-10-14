"""Reading suggestions never creates settings, versions or analysis jobs."""

from django.utils.translation import override
from rest_framework.test import APIRequestFactory, force_authenticate

from .models import QualityCriteriaVersion, QualityJob, QualitySettings
from .test_base import QualityTestBase
from .views import QualitySettingsView


class QualitySettingsSuggestionsTests(QualityTestBase):
    def request(self, method="get", data=None):
        factory = APIRequestFactory()
        request = factory.get("/") if method == "get" else factory.put("/", data, format="json")
        request.tenant_context = self.context
        force_authenticate(request, user=self.context.actor_user)
        return QualitySettingsView.as_view()(request)

    def test_read_only_baseline_suggestions_are_in_organization_language(self):
        self.organization.language = "ru"
        self.organization.save(update_fields=["language"])
        with override("en"):
            response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["enabled"])
        self.assertIsNone(response.data["criteriaVersion"])
        self.assertEqual(response.data["criteria"], [])
        suggestions = response.data["suggestedCriteria"]
        self.assertEqual([item["name"] for item in suggestions], ["Приветствие", "Решение вопроса", "Тон общения"])
        self.assertEqual([item["description"] for item in suggestions], [
            "Сотрудник поздоровался и представился в первом сообщении.",
            "Вопрос клиента решён или передан с понятным следующим шагом.",
            "Вежливо, без канцелярита и давления.",
        ])
        self.assertEqual([item["scale"] for item in suggestions], [["Да", "Нет"], [1, 2, 3, 4, 5], [1, 2, 3, 4, 5]])
        self.assertFalse(QualitySettings.objects.exists())
        self.assertFalse(QualityCriteriaVersion.objects.exists())
        self.assertFalse(QualityJob.objects.exists())
        self.organization.language = "en"
        self.organization.save(update_fields=["language"])
        with override("ru"):
            self.assertEqual(self.request().data["suggestedCriteria"][0]["name"], "Greeting")

    def test_explicit_save_edit_and_clear_keep_versions_and_do_not_enable(self):
        proposed = self.request().data["suggestedCriteria"]
        proposed[0]["description"] = "Edited before saving"
        response = self.request("put", {"enabled": False, "criteria": proposed})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["enabled"])
        self.assertEqual(response.data["criteria"], proposed)
        self.assertIsNone(response.data["suggestedCriteria"])
        self.assertEqual(response.data["criteriaVersion"], 1)
        first = QualityCriteriaVersion.objects.get(version=1)
        response = self.request("put", {"enabled": False, "criteria": []})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["criteriaVersion"], 2)
        self.assertEqual(response.data["criteria"], [])
        self.assertIsNone(self.request().data["suggestedCriteria"])
        self.assertEqual(self.request("put", {"enabled": True}).status_code, 400)
        first.refresh_from_db()
        self.assertEqual(first.criteria, proposed)
        self.assertEqual(QualityCriteriaVersion.objects.count(), 2)
        self.assertFalse(QualitySettings.objects.get().enabled)
        self.assertFalse(QualityJob.objects.exists())
