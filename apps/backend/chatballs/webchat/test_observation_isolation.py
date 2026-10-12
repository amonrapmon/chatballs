from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from chatballs.channels.models import Channel
from chatballs.identity.models import Organization
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic
from chatballs.webchat.models import WebSession
from chatballs.webchat.observation_models import VisitorObservation
from chatballs.webchat.observations import record_signal
from chatballs.webchat.sessions import issue_session
from chatballs.webchat.testing import create_web_widget

URL = "/api/v1/webchat/observations/"


class VisitorObservationIsolationTests(TransactionTestCase):
    def setUp(self):
        self.sessions = []
        self.tokens = []
        for slug in ("observation-first", "observation-second"):
            organization = Organization.objects.create(name=slug, slug=slug)
            widget = create_web_widget(Channel.objects.create(
                organization=organization, code="web", name="Web",
            ))
            context = TenantContext.for_resource(organization)
            with tenant_atomic(context):
                result = issue_session(context=context, widget=widget)
                session = WebSession.objects.get(organization=organization)
                record_signal(session, {"tabId": str(uuid4()), "sequence": 1, "kind": "widget_open"})
            self.sessions.append(session)
            self.tokens.append(result["token"])

    def test_runtime_rls_and_foreign_session_guard(self):
        first, second = self.sessions
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE chatballs_runtime_app")
        try:
            with transaction.atomic():
                self.assertEqual(VisitorObservation.objects.count(), 0)
            for session in self.sessions:
                with tenant_atomic(session.organization_id):
                    self.assertEqual(VisitorObservation.objects.count(), 1)
                    self.assertEqual(VisitorObservation.objects.get().session_id, session.pk)
            with tenant_atomic(first.organization_id):
                self.assertEqual(VisitorObservation.objects.filter(session_id=second.pk).update(sequence=2), 0)
                with self.assertRaises(DatabaseError), transaction.atomic():
                    # bulk_create bypasses model validation: PostgreSQL must
                    # still reject a foreign WebSession even with a valid tenant key.
                    VisitorObservation.objects.bulk_create([VisitorObservation(
                        organization_id=first.organization_id, session_id=second.pk,
                        tab_id=uuid4(), sequence=1, received_at=first.created_at,
                    )])
            client = APIClient()
            response = client.post(URL, {
                "tabId": str(uuid4()), "sequence": 1, "kind": "heartbeat",
            }, format="json", headers={"Authorization": f"Bearer {self.tokens[0]}"})
            self.assertEqual(response.status_code, 200, response.content)
            response = client.get(URL, headers={"Authorization": f"Bearer {self.tokens[0]}"})
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(len(response.json()["tabs"]), 2)
            response = client.get(URL, headers={"Authorization": f"Bearer {self.tokens[1]}"})
            self.assertEqual(len(response.json()["tabs"]), 1)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def test_concurrent_first_signals_keep_highest_sequence(self):
        session = self.sessions[0]
        tab = str(uuid4())
        barrier = Barrier(2)

        def send(sequence, kind):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                with tenant_atomic(session.organization_id):
                    accepted, _ = record_signal(session, {
                        "tabId": tab, "sequence": sequence, "kind": kind,
                    })
                return accepted
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            low = executor.submit(send, 1, "widget_open")
            high = executor.submit(send, 2, "widget_close")
            low.result(timeout=15)
            self.assertTrue(high.result(timeout=15))
        rows = VisitorObservation.objects.filter(session=session, tab_id=tab)
        self.assertEqual(rows.count(), 1)
        self.assertEqual((rows.get().sequence, rows.get().widget_state), (2, "closed"))
