import time
from datetime import timedelta
from uuid import uuid4

from rest_framework.test import APIClient

from chatballs.conversations.lifecycle_services import close_conversation
from chatballs.conversations.maintenance import close_stale_conversations
from chatballs.ratings.models import RatingRequest
from chatballs.ratings.settings_service import update_settings
from chatballs.ratings.test_support import RatingTestBase
from chatballs.ratings.web_delivery import deliver_due_requests, session_requests
from chatballs.tenancy.context import TenantActorKind, TenantContext
from chatballs.webchat.message_history import messages_payload


class RatingDeliveryTests(RatingTestBase):
    def test_actual_close_and_worker_poll_are_idempotent_with_delay(self):
        self.policy.delay_seconds = 1
        self.policy.save()
        operation = uuid4()
        close_conversation(context=self.context, conversation_id=self.conversation.pk, operation_id=operation)
        close_conversation(context=self.context, conversation_id=self.conversation.pk, operation_id=operation)
        self.assertEqual(RatingRequest.objects.count(), 1)
        request = RatingRequest.objects.get()
        self.assertEqual(request.due_at - request.completion.occurred_at, timedelta(seconds=1))
        self.assertEqual(deliver_due_requests(self.context), 0)
        time.sleep(1.1)
        self.assertEqual(deliver_due_requests(self.context), 1)
        first = session_requests(self.session)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["text"], self.policy.text)
        self.assertEqual(first[0]["scale"], self.scale)
        self.assertEqual(deliver_due_requests(self.context), 0)
        self.assertEqual(session_requests(self.session), first)
        self.assertEqual(messages_payload(self.session, 0)["ratingRequests"], first)
        from chatballs.webchat.sessions import hash_session_token

        self.session.token_hash = hash_session_token("web-rating-test-session")
        self.session.save(update_fields=["token_hash"])
        client = APIClient()
        response = client.get("/api/v1/webchat/messages/", HTTP_AUTHORIZATION="Bearer web-rating-test-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["ratingRequests"], first)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {first[0]['credential']}")
        question = client.get("/api/v1/ratings/")
        self.assertEqual(question.status_code, 200)
        self.assertEqual(question.data["text"], self.policy.text)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.lifecycle, "CLOSED")
        self.assertFalse(self.conversation.messages.exists())

    def test_disabling_and_deleting_cancel_pending_delivery(self):
        request = self.scheduled()
        update_settings(self.context, {"enabled": False})
        request.refresh_from_db()
        self.assertIsNotNone(request.cancelled_at)
        update_settings(self.context, {"enabled": True})
        self.assertEqual(deliver_due_requests(self.context), 0)
        self.assertEqual(session_requests(self.session), [])
        event = self.row(event_type="CLOSED")
        event.save()
        self.assertEqual(RatingRequest.objects.count(), 2)
        self.conversation.delete()
        self.assertFalse(RatingRequest.objects.exists())
        self.assertEqual(deliver_due_requests(self.context), 0)

    def test_unavailable_or_unsupported_delivery_does_not_send(self):
        request = self.scheduled()
        self.widget.status = "DISABLED"
        self.widget.save()
        self.assertEqual(deliver_due_requests(self.context), 0)
        request.refresh_from_db()
        self.assertIsNotNone(request.cancelled_at)
        self.widget.status = "PUBLISHED"
        self.widget.save()
        self.connection.provider = "TELEGRAM"
        self.connection.save()
        event = self.row(event_type="CLOSED", transport="TELEGRAM")
        event.save()
        other = RatingRequest.objects.get(completion=event)
        self.assertEqual(deliver_due_requests(self.context), 0)
        other.refresh_from_db()
        self.assertIsNotNone(other.cancelled_at)

    def test_session_binding_never_returns_another_widget_or_customer_request(self):
        self.scheduled()
        deliver_due_requests(self.context)
        self.assertEqual(len(session_requests(self.session)), 1)
        from chatballs.webchat.models import WebSession
        foreign_session = WebSession(pk=self.session.pk + 1000, organization_id=self.organization.pk)
        self.assertEqual(session_requests(foreign_session), [])
        foreign_session.pk = self.session.pk
        foreign_session.organization_id = self.foreign.pk
        self.assertEqual(session_requests(foreign_session), [])

    def test_settings_validation_permissions_and_disabled_defaults_over_http(self):
        client = APIClient()
        path = f"/api/v1/organizations/{self.organization.public_id}/ratings/settings/"
        client.force_login(self.user)
        self.policy.delete()
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"enabled": False, "scale": [], "text": "", "delaySeconds": 0})
        self.assertEqual(client.patch(path, {"enabled": True}, format="json").status_code, 400)
        for changes in ({"delaySeconds": True}, {"delaySeconds": -1}, {"scale": []},
                        {"text": ""}, {"enabled": "true"}):
            payload = {"enabled": True, "scale": self.scale, "text": "Configured question", **changes}
            self.assertEqual(client.patch(path, payload, format="json").status_code, 400)
        response = client.patch(path, {"enabled": True, "scale": self.scale, "text": "Configured question"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.member.role = "EMPLOYEE"
        self.member.save()
        self.assertEqual(client.get(path).status_code, 403)
        self.assertEqual(client.patch(path, {"enabled": False}, format="json").status_code, 403)

    def test_disabled_or_incomplete_config_does_not_schedule_and_auto_close_does(self):
        self.policy.enabled = False
        self.policy.save()
        self.completion()
        self.assertFalse(RatingRequest.objects.exists())
        self.policy.enabled = True
        self.policy.text = ""
        self.policy.save()
        event = self.row(event_type="CLOSED")
        event.save()
        self.assertFalse(RatingRequest.objects.exists())
        self.policy.text = "Configured question"
        self.policy.save()
        self.conversation.lifecycle = "OPEN"
        self.conversation.save()
        system = TenantContext.for_resource(self.organization, actor_kind=TenantActorKind.SYSTEM)
        self.assertEqual(close_stale_conversations(system, days=0), 1)
        self.assertEqual(RatingRequest.objects.count(), 1)
