from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from chatballs import presence
from chatballs.identity.models import HumanUser, OrganizationMembership
from chatballs.identity.work_status_codes import WorkStatus
from chatballs.identity.work_status_intervals import own_work_status_intervals
from chatballs.identity.work_status_models import WorkStatusOperation
from chatballs.identity.work_status_services import (
    WorkStatusVersionConflict,
    own_work_status_history,
)
from chatballs.identity.work_status_testing import WorkStatusTestBase
from chatballs.tenancy.context import TenantContext


class WorkStatusTests(WorkStatusTestBase):
    def test_membership_is_independent_of_organization_and_presence(self):
        before = timezone.now()
        operation = self.change()
        self.assertLessEqual(before, operation.changed_at)
        self.assertLessEqual(operation.changed_at, timezone.now())
        self.assertEqual(operation.recorded_at, operation.changed_at)
        self.assertEqual((operation.previous_status, operation.status, operation.version), (WorkStatus.UNAVAILABLE, WorkStatus.READY, 1))
        presence.touch(self.organization.pk, self.user.pk)
        self.membership.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.membership.work_status, WorkStatus.READY)
        self.assertEqual((self.other.work_status, self.other.work_status_version, self.other.work_status_changed_at), (WorkStatus.UNAVAILABLE, 0, None))
        self.assertEqual(own_work_status_history(context=TenantContext.for_membership(self.other)), [])
        self.assertEqual(own_work_status_history(context=self.context), [operation])
        self.assertIn(self.user.pk, presence.online_user_ids(self.organization.pk, [self.user.pk]))
        self.change(WorkStatus.BREAK, 1)
        self.assertIn(self.user.pk, presence.online_user_ids(self.organization.pk, [self.user.pk]))

    def test_same_status_and_key_replay_do_not_duplicate_intervals(self):
        key = uuid4()
        initial = self.change(WorkStatus.UNAVAILABLE, key=key)
        self.assertFalse(initial.changed)
        self.assertIsNone(initial.changed_at)
        self.assertEqual(own_work_status_history(context=self.context), [])
        first = self.change()
        noop_key = uuid4()
        noop = self.change(WorkStatus.READY, 1, noop_key)
        self.assertEqual((noop.version, noop.changed_at), (first.version, first.changed_at))
        self.change(WorkStatus.BUSY, 1)
        replay = self.change(WorkStatus.READY, 1, noop_key)
        self.assertEqual(replay.pk, noop.pk)
        self.assertEqual(self.change(WorkStatus.READY, 0, first.operation_id).pk, first.pk)
        self.assertEqual(self.change(WorkStatus.UNAVAILABLE, 0, key).pk, initial.pk)
        self.assertEqual(len(own_work_status_history(context=self.context)), 2)
        self.assertEqual(WorkStatusOperation.objects.count(), 4)
        self.membership.refresh_from_db()
        self.assertEqual((self.membership.work_status, self.membership.work_status_version), (WorkStatus.BUSY, 2))
        # The same key belongs to a different membership independently.
        other = self.change(key=first.operation_id, context=TenantContext.for_membership(self.other))
        self.assertNotEqual(other.pk, first.pk)

    def test_stale_version_rejected_even_for_same_current_status(self):
        self.change()
        for status in (WorkStatus.READY, WorkStatus.BREAK):
            with self.subTest(status=status), self.assertRaises(WorkStatusVersionConflict):
                self.change(status, 0)
        self.assertEqual(WorkStatusOperation.objects.count(), 1)

    def test_operation_failure_rolls_back_membership(self):
        with patch.object(WorkStatusOperation.objects, "create", side_effect=RuntimeError("write failed")), self.assertRaises(RuntimeError):
            self.change()
        self.membership.refresh_from_db()
        self.assertEqual((self.membership.work_status, self.membership.work_status_version, self.membership.work_status_changed_at), (WorkStatus.UNAVAILABLE, 0, None))
        self.assertFalse(WorkStatusOperation.objects.exists())

    def test_fresh_block_inactive_user_and_forged_context_are_denied(self):
        contexts = [
            replace(self.context, organization=self.foreign),
            replace(self.context, membership=self.other),
            replace(self.context, actor_user=None),
        ]
        for context in contexts:
            with self.subTest(context=context), self.assertRaises(PermissionDenied):
                self.change(context=context)
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(blocked_at=timezone.now())
        with self.assertRaises(PermissionDenied):
            self.change()
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(blocked_at=None)
        HumanUser.objects.filter(pk=self.user.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.change()
        self.assertFalse(WorkStatusOperation.objects.exists())

    def test_input_validation_does_not_write(self):
        for kwargs in ({"status": "ONLINE"}, {"version": True}, {"version": -1}, {"key": "bad"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                self.change(**kwargs)
        self.assertFalse(WorkStatusOperation.objects.exists())

    def test_intervals_clip_half_open_period_and_do_not_backfill(self):
        start = timezone.now()
        self.assertEqual(own_work_status_intervals(context=self.context, start=start - timedelta(days=30), end=start), [])
        with patch("chatballs.identity.work_status_services.timezone.now", return_value=start):
            self.change()
        middle = start + timedelta(hours=1)
        with patch("chatballs.identity.work_status_services.timezone.now", return_value=middle):
            self.change(WorkStatus.BREAK, 1)
        intervals = own_work_status_intervals(context=self.context, start=start - timedelta(days=1), end=middle)
        self.assertEqual([(i.status, i.start, i.end) for i in intervals], [(WorkStatus.READY, start, middle)])
        left, right = start + timedelta(minutes=30), middle + timedelta(minutes=30)
        intervals = own_work_status_intervals(context=self.context, start=left, end=right)
        self.assertEqual([(i.status, i.start, i.end) for i in intervals], [(WorkStatus.READY, left, middle), (WorkStatus.BREAK, middle, right)])
        for left, right in ((start, start), (middle, start), (start.replace(tzinfo=None), middle)):
            with self.subTest(left=left), self.assertRaises(ValidationError):
                own_work_status_intervals(context=self.context, start=left, end=right)
