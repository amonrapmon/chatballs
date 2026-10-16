from datetime import timedelta
from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from chatballs.channels.models import Channel
from chatballs.conversations.models import Conversation, Message
from chatballs.events.models import InboxEvent, OutboxEvent
from chatballs.identity.models import Organization
from chatballs.webchat.models import WebSession
from chatballs.webchat.observation_models import VisitorObservation
from chatballs.webchat.observations import MAX_TABS_PER_SESSION, observation_payload
from chatballs.webchat.testing import create_web_widget

URL = "/api/v1/webchat/observations/"


class VisitorObservationApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.organization = Organization.objects.create(name="Observations", slug="observations")
        self.widget = create_web_widget(Channel.objects.create(
            organization=self.organization, code="observations", name="Web",
        ))
        self.client = APIClient()
        self.token, self.session = self.issue_session()
        self.tab = str(uuid4())

    def issue_session(self, widget=None):
        response = self.client.post(
            "/api/v1/webchat/session/", {"widgetKey": (widget or self.widget).public_key}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["token"], WebSession.objects.latest("id")

    def signal(self, kind="heartbeat", sequence=1, tab=None, token=None, **extra):
        return self.client.post(URL, {
            "tabId": tab or self.tab, "sequence": sequence, "kind": kind, **extra,
        }, format="json", headers={"Authorization": f"Bearer {token or self.token}"})

    def read(self, token=None):
        return self.client.get(URL, headers={"Authorization": f"Bearer {token or self.token}"})

    def test_axis_change_times_are_not_reset_by_heartbeats_or_other_axes(self):
        self.signal("widget_close", 1)
        old = timezone.now() - timedelta(minutes=5)
        VisitorObservation.objects.filter(session=self.session).update(widget_changed_at=old)
        self.signal("page_hidden", 2)
        self.signal("heartbeat", 3)
        row = self.read().json()["tabs"][0]
        self.assertEqual(row["widgetChangedAt"], old.isoformat())
        self.assertIsNotNone(row["pageChangedAt"])
        heartbeat = timezone.now() - timedelta(seconds=120)
        VisitorObservation.objects.filter(session=self.session).update(heartbeat_at=heartbeat)
        lost = self.read().json()["tabs"][0]
        self.assertEqual(lost["connection"], "lost")
        self.assertEqual(lost["connectionChangedAt"], (heartbeat + timedelta(seconds=90)).isoformat())
        self.signal("heartbeat", 4)
        restored = self.read().json()["tabs"][0]
        self.assertEqual(restored["connection"], "connected")
        self.assertNotEqual(restored["connectionChangedAt"], row["connectionChangedAt"])

    def test_only_current_session_credentials_are_accepted(self):
        for method in (self.client.get, self.client.post):
            self.assertEqual(method(URL).status_code, 401)
        self.assertEqual(self.signal(token="invalid").status_code, 401)
        self.assertEqual(self.client.get(URL, {"token": self.token}).status_code, 401)
        self.assertEqual(self.client.post(URL, {"token": self.token}, format="json").status_code, 401)
        self.assertEqual(self.client.post(URL, [], format="json").status_code, 401)
        WebSession.objects.filter(pk=self.session.pk).update(last_seen_at=timezone.now() - timedelta(days=365))
        self.assertEqual(self.signal().status_code, 401)
        self.assertEqual(self.read().status_code, 401)
        self.assertFalse(VisitorObservation.objects.exists())

    def test_order_duplicates_and_tabs_are_independent(self):
        newest = self.signal("widget_close", 5).json()
        self.assertTrue(newest["accepted"])
        for sequence, kind in ((4, "widget_open"), (5, "heartbeat")):
            rejected = self.signal(kind, sequence).json()
            self.assertFalse(rejected["accepted"])
            self.assertEqual(rejected["observation"], newest["observation"])
        other_tab = str(uuid4())
        self.assertTrue(self.signal("widget_open", 1, tab=other_tab).json()["accepted"])
        rows = {row["tabId"]: row for row in self.read().json()["tabs"]}
        self.assertEqual(rows[self.tab]["widget"], "closed")
        self.assertEqual(rows[other_tab]["widget"], "open")
        self.assertEqual(VisitorObservation.objects.count(), 2)

    def test_session_and_tenant_from_payload_cannot_redirect_signal(self):
        other_org = Organization.objects.create(name="Other", slug="observations-other")
        other_widget = create_web_widget(Channel.objects.create(
            organization=other_org, code="observations", name="Other web",
        ))
        token, other_session = self.issue_session(other_widget)
        self.signal("widget_close", 10)
        response = self.signal("widget_open", 1, token=token,
                               sessionId=self.session.pk, organizationId=self.organization.pk)
        self.assertTrue(response.json()["accepted"])
        self.assertEqual(VisitorObservation.objects.get(session=other_session).organization_id, other_org.pk)
        self.assertEqual(self.read().json()["tabs"][0]["widget"], "closed")
        self.assertEqual(self.read(token).json()["tabs"][0]["widget"], "open")
        # The same tab UUID is also independent between sessions of one widget.
        third_token, third_session = self.issue_session()
        self.assertTrue(self.signal("heartbeat", 1, token=third_token).json()["accepted"])
        self.assertEqual(VisitorObservation.objects.filter(session=third_session).count(), 1)

    def test_axes_lifecycle_and_uncertain_departure_do_not_mix(self):
        self.signal("heartbeat", 1)
        expected = {"widget": "unknown", "page": "unknown", "connection": "connected"}
        for sequence, (kind, field, value) in enumerate((
            ("widget_open", "widget", "open"),
            ("widget_close", "widget", "closed"),
            ("page_hidden", "page", "hidden"),
            ("page_freeze", "page", "frozen"),
            ("page_resume", "page", "resumed"),
            ("page_hide", "page", "pagehide"),
            ("connection_lost", "connection", "lost"),
            ("page_show", "page", "pageshow"),
            ("page_visible", "page", "visible"),
            ("heartbeat", "connection", "connected"),
        ), start=2):
            row = self.signal(kind, sequence).json()["observation"]
            expected[field] = value
            self.assertEqual({key: row[key] for key in expected}, expected)
            self.assertEqual(row["departure"], "unknown")

    def test_heartbeat_boundary_stale_delivery_and_recovery(self):
        self.signal("heartbeat", 1)
        row = VisitorObservation.objects.get()
        self.assertEqual(observation_payload(row, now=row.heartbeat_at + timedelta(seconds=89))["connection"], "connected")
        self.assertEqual(observation_payload(row, now=row.heartbeat_at + timedelta(seconds=90))["connection"], "lost")
        old = timezone.now() - timedelta(seconds=91)
        VisitorObservation.objects.update(heartbeat_at=old)
        self.assertFalse(self.signal("heartbeat", 1).json()["accepted"])
        self.signal("widget_close", 2)
        self.assertEqual(self.read().json()["tabs"][0]["connection"], "lost")
        row.refresh_from_db()
        self.assertEqual(row.heartbeat_at, old)
        response = self.signal("heartbeat", 3).json()["observation"]
        self.assertEqual(response["connection"], "connected")
        self.assertEqual(response["widget"], "closed")
        self.assertEqual(response["departure"], "unknown")

    def test_no_signals_is_unknown_and_response_has_no_session_secrets(self):
        payload = self.read().json()
        self.assertEqual(payload, {"tabs": [], "heartbeatIntervalSeconds": 30, "heartbeatTimeoutSeconds": 90})
        self.signal("widget_close")
        payload = self.read().json()
        row = payload["tabs"][0]
        self.assertEqual((row["page"], row["connection"], row["departure"]), ("unknown", "unknown", "unknown"))
        self.assertNotIn(self.token, str(payload))
        self.assertNotIn(self.session.token_hash, str(payload))

    def test_signals_do_not_close_conversations_or_create_mail_or_events(self):
        conversation = Conversation.objects.create(
            organization=self.organization, channel=self.widget.integration.channel,
            connection=self.widget.integration, contact=self.session.identity.contact,
        )
        before = Conversation.objects.filter(pk=conversation.pk).values().get()
        counts = [model.objects.count() for model in (Message, InboxEvent, OutboxEvent)]
        for sequence, kind in enumerate(("widget_close", "page_hidden", "page_hide", "connection_lost"), start=1):
            self.assertEqual(self.signal(kind, sequence).status_code, 200)
        self.assertEqual(Conversation.objects.filter(pk=conversation.pk).values().get(), before)
        self.assertEqual([model.objects.count() for model in (Message, InboxEvent, OutboxEvent)], counts)

    def test_invalid_signals_do_not_write_state(self):
        cases = [
            {"sequence": 0}, {"sequence": -1}, {"sequence": True}, {"sequence": "1"},
            {"sequence": 1.5}, {"sequence": 2**63}, {"kind": "leave_confirmed"},
            {"kind": []}, {"tabId": "invalid"}, {"tabId": None},
            {"tabId": "00000000-0000-0000-0000-000000000000"},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                response = self.client.post(URL, {
                    "tabId": self.tab, "sequence": 1, "kind": "heartbeat", **changes,
                }, format="json", headers={"Authorization": f"Bearer {self.token}"})
                self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(VisitorObservation.objects.exists())

    def test_tab_limit_keeps_existing_tab_usable(self):
        self.signal()
        VisitorObservation.objects.bulk_create([
            VisitorObservation(organization=self.organization, session=self.session,
                               tab_id=uuid4(), sequence=1, received_at=timezone.now())
            for _ in range(MAX_TABS_PER_SESSION - 1)
        ])
        self.assertEqual(self.signal(tab=str(uuid4())).status_code, 400)
        self.assertTrue(self.signal("widget_close", 2).json()["accepted"])

    def test_observations_use_existing_session_write_throttle(self):
        original = SimpleRateThrottle.THROTTLE_RATES
        SimpleRateThrottle.THROTTLE_RATES = {**original, "webchat_session_write": "1/min"}
        cache.clear()
        try:
            self.assertEqual(self.signal().status_code, 200)
            self.assertEqual(self.signal(sequence=2).status_code, 429)
        finally:
            SimpleRateThrottle.THROTTLE_RATES = original
            cache.clear()
