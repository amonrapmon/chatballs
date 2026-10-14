"""Предложение настроек не изменяет сохранённую политику и язык клиента."""

from rest_framework.test import APIClient

from chatballs.conversations.domain_event_test_base import DomainEventTestBase
from chatballs.ratings.models import RatingRequest, RatingSettings


class RatingSettingsDefaultsTests(DomainEventTestBase):
    def setUp(self):
        self.organization.language = "ru"
        self.organization.save(update_fields=["language"])
        self.client = APIClient()
        self.client.force_login(self.user)
        self.path = f"/api/v1/organizations/{self.organization.public_id}/ratings/settings/"

    def test_initial_form_has_complete_suggestions_without_enabling_or_writing(self):
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["enabled"])
        self.assertEqual(response.data["scale"], [])
        self.assertEqual(response.data["text"], "")
        self.assertIsNone(response.data["updatedAt"])
        defaults = response.data["defaults"]
        self.assertEqual([choice["value"] for choice in defaults["scale"]], [1, 2, 3, 4, 5])
        self.assertTrue(all(choice["label"] for choice in defaults["scale"]))
        self.assertTrue(defaults["text"])
        self.assertEqual(defaults["delaySeconds"], 600)
        self.assertFalse(RatingSettings.objects.filter(organization=self.organization).exists())
        self.assertFalse(RatingRequest.objects.exists())

    def test_customer_suggestions_use_organization_language_not_employee_language(self):
        self.organization.language = "en"
        self.organization.save(update_fields=["language"])
        self.user.ui_language = "ru"
        self.user.save(update_fields=["ui_language"])
        defaults = self.client.get(self.path).data["defaults"]
        self.assertEqual(defaults["scale"][-1]["label"], "Excellent")
        self.assertIn("Please rate the conversation", defaults["text"])

    def test_suggestions_can_be_enabled_saved_and_reloaded_without_resetting_custom_values(self):
        defaults = self.client.get(self.path).data["defaults"]
        response = self.client.patch(self.path, {**defaults, "enabled": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["enabled"])
        self.assertIsNotNone(response.data["updatedAt"])
        saved = self.client.get(self.path).data
        for key, value in defaults.items():
            self.assertEqual(saved[key], value)
        self.assertNotIn("defaults", saved)
        self.assertFalse(RatingRequest.objects.exists())

        custom = {"enabled": False, "text": "Our custom question", "delaySeconds": 0}
        self.assertEqual(self.client.patch(self.path, custom, format="json").status_code, 200)
        saved = self.client.get(self.path).data
        self.assertEqual(saved["text"], custom["text"])
        self.assertEqual(saved["delaySeconds"], 0)
        self.assertEqual(saved["scale"], defaults["scale"])
        self.assertNotIn("defaults", saved)
