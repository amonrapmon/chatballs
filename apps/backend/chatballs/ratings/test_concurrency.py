from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from chatballs.conversations.domain_event_test_base import DomainEventTestBase
from chatballs.events.models import OutboxEvent
from chatballs.ratings.credentials import credential_for
from chatballs.ratings.models import CustomerRating
from chatballs.ratings.test_support import RatingTestBase
from chatballs.ratings.web_delivery import deliver_due_requests


class RatingConcurrencyTests(TransactionTestCase):
    row = DomainEventTestBase.row
    completion = RatingTestBase.completion
    scheduled = RatingTestBase.scheduled

    def setUp(self):
        DomainEventTestBase.setUpTestData.__func__(type(self))
        RatingTestBase.setUp(self)
        self.target = self.scheduled()

    def parallel(self, operation):
        barrier = Barrier(2)

        def run(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operation(index)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run, index) for index in range(2)]
            return [future.result(timeout=20) for future in futures]

    def post(self, value):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {credential_for(self.target)}")
        return client.post("/api/v1/ratings/", {"value": value}, format="json").status_code

    def test_concurrent_workers_and_identical_submissions_are_idempotent(self):
        self.assertEqual(sorted(self.parallel(lambda _: deliver_due_requests(self.context))), [0, 1])
        self.assertEqual(sorted(self.parallel(lambda _: self.post(5))), [200, 201])
        self.assertEqual(CustomerRating.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(event_type="ratings.received").count(), 1)

    def test_concurrent_replacement_is_conflict(self):
        deliver_due_requests(self.context)
        self.assertEqual(sorted(self.parallel(lambda index: self.post(index + 4))), [201, 409])
        self.assertEqual(CustomerRating.objects.count(), 1)
