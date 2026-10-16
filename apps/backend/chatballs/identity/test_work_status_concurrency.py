from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from django.db import connection, connections

from chatballs.identity.work_status_codes import WorkStatus
from chatballs.identity.work_status_models import WorkStatusOperation
from chatballs.identity.work_status_services import WorkStatusVersionConflict
from chatballs.identity.work_status_testing import WorkStatusTestBase
from chatballs.tenancy.database import tenant_atomic


class WorkStatusConcurrencyTests(WorkStatusTestBase):
    def run_concurrently(self, requests):
        barrier = Barrier(len(requests))

        def run(request):
            try:
                barrier.wait(timeout=10)
                with tenant_atomic(self.context):
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
                        cursor.execute("SET LOCAL lock_timeout = '10s'")
                    try:
                        return self.change(**request)
                    except WorkStatusVersionConflict:
                        return "conflict"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            futures = [pool.submit(run, request) for request in requests]
            return [future.result(timeout=20) for future in futures]

    def test_different_requests_with_same_version_have_one_winner(self):
        results = self.run_concurrently([
            {"status": WorkStatus.READY}, {"status": WorkStatus.BREAK},
        ])
        self.assertEqual(results.count("conflict"), 1)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.work_status_version, 1)
        self.assertEqual(WorkStatusOperation.objects.count(), 1)
        winner = next(result for result in results if result != "conflict")
        self.assertEqual((winner.status, winner.changed_at), (self.membership.work_status, self.membership.work_status_changed_at))

    def test_concurrent_key_replay_returns_one_operation(self):
        key = uuid4()
        results = self.run_concurrently([{"key": key}, {"key": key}])
        self.assertEqual(results[0].pk, results[1].pk)
        self.assertEqual(WorkStatusOperation.objects.count(), 1)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.work_status_version, 1)
