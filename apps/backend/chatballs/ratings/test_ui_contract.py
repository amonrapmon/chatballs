"""Baseline data, scoped access and cancellation on actual customer messages."""

from rest_framework.test import APIClient

from chatballs.conversations.models import Message
from chatballs.ratings.card import conversation_card
from chatballs.ratings.credentials import credential_for
from chatballs.ratings.settings_service import update_settings
from chatballs.ratings.test_support import RatingTestBase
from chatballs.ratings.web_delivery import deliver_due_requests


class RatingUIContractTests(RatingTestBase):
    def test_company_presentation_and_saved_by_without_private_context(self):
        self.widget.allowed_origins = ["https://company.example"]
        self.widget.presentation_config = {"accent": "#0f766e"}
        self.widget.save()
        target = self.scheduled()
        deliver_due_requests(self.context)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {credential_for(target)}")
        response = client.get("/api/v1/ratings/")
        self.assertEqual(response.status_code, 200)
        presentation = response.data["presentation"]
        self.assertEqual(presentation["name"], self.organization.name)
        self.assertEqual(presentation["siteUrl"], "https://company.example")
        self.assertEqual(presentation["accent"], "#0f766e")
        self.assertEqual(set(presentation), {"name", "accent", "siteUrl", "conversationDate", "language"})
        client.credentials()
        client.force_login(self.user)
        path = f"/api/v1/organizations/{self.organization.public_id}/ratings/settings/"
        response = client.patch(path, {"text": "Changed question"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["updatedBy"], self.user.full_name)
        self.assertIsNotNone(response.data["updatedAt"])

    def test_empty_sent_and_disabled_cards_and_scoped_responders(self):
        self.assertIsNone(conversation_card(self.context, self.conversation.pk)["request"])
        update_settings(self.context, {"enabled": False})
        self.assertFalse(conversation_card(self.context, self.conversation.pk)["enabled"])
        update_settings(self.context, {"enabled": True})
        self.row(event_type="PUBLIC_REPLY").save()
        target = self.scheduled()
        deliver_due_requests(self.context)
        card = conversation_card(self.context, self.conversation.pk)
        self.assertIsNotNone(card["request"]["sentAt"])
        self.assertEqual(card["results"], [])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {credential_for(target)}")
        self.assertEqual(client.post("/api/v1/ratings/", {"value": 4}, format="json").status_code, 201)
        card = conversation_card(self.context, self.conversation.pk)
        self.assertEqual(card["results"][0]["responders"][0]["id"], self.user.pk)
        self.assertNotIn("credential", str(card))
        update_settings(self.context, {"enabled": False})
        # Historical results survive disabling.
        self.assertEqual(len(conversation_card(self.context, self.conversation.pk)["results"]), 1)

    def test_disabling_revokes_an_unanswered_public_question(self):
        target = self.scheduled()
        deliver_due_requests(self.context)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {credential_for(target)}")
        self.assertEqual(client.get("/api/v1/ratings/").status_code, 200)
        update_settings(self.context, {"enabled": False})
        self.assertEqual(client.get("/api/v1/ratings/").status_code, 404)
        update_settings(self.context, {"enabled": True})
        self.assertEqual(client.get("/api/v1/ratings/").status_code, 404)

    def test_new_customer_message_cancels_pending_but_not_delivered_request(self):
        target = self.scheduled()
        Message.objects.create(organization=self.organization, conversation=self.conversation,
                               author_type="CONTACT", text="Customer returns")
        target.refresh_from_db()
        self.assertIsNotNone(target.cancelled_at)
        self.assertEqual(deliver_due_requests(self.context), 0)
        next_target = self.scheduled()
        deliver_due_requests(self.context)
        Message.objects.create(organization=self.organization, conversation=self.conversation,
                               author_type="CONTACT", text="Another customer message")
        next_target.refresh_from_db()
        self.assertIsNone(next_target.cancelled_at)

    def test_public_validation_uses_company_language(self):
        from chatballs.i18n import t

        self.organization.language = "en"
        self.organization.save(update_fields=["language"])
        target = self.scheduled()
        deliver_due_requests(self.context)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {credential_for(target)}")
        response = client.post("/api/v1/ratings/", {"value": 6}, format="json", HTTP_ACCEPT_LANGUAGE="ru")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["detail"]), t("ratings.invalid_response", language="en"))
