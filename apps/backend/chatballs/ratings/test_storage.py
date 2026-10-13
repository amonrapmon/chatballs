from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from chatballs.ratings.models import CustomerRating, RatingRequest, RatingSettings
from chatballs.ratings.scheduling import schedule_request
from chatballs.ratings.test_support import RatingTestBase
from chatballs.ratings.web_delivery import deliver_due_requests
from chatballs.tenancy.database import tenant_atomic


class RatingStorageTests(RatingTestBase):
    def test_defaults_and_snapshot_attribution_ignore_responsibility(self):
        empty = RatingSettings(organization=self.foreign)
        self.assertFalse(empty.enabled)
        self.assertEqual(empty.scale, [])
        self.row(event_type="PUBLIC_REPLY").save()
        self.row(event_type="PUBLIC_REPLY").save()
        target = self.scheduled()
        self.assertEqual(target.responder_ids, [self.user.pk])
        self.assertEqual(target.scale, self.scale)
        self.policy.text = "Future question"
        self.policy.scale[0]["label"] = "New label"
        self.policy.save()
        target.refresh_from_db()
        self.assertEqual(target.text, "Test customer question")
        self.assertEqual(target.scale[0]["label"], "1")
        self.assertEqual(schedule_request(target.completion).pk, target.pk)
        self.assertEqual(RatingRequest.objects.count(), 1)

    def test_assignment_alone_and_ai_do_not_become_responders(self):
        self.row(event_type="ASSIGNED").save()
        self.row(event_type="PUBLIC_REPLY", actor_kind="AI", initiated_by_id=None).save()
        self.assertEqual(self.scheduled().responder_ids, [])

    def test_public_messages_before_journal_are_included_without_inventing_facts(self):
        from chatballs.conversations.models import Message

        Message.objects.create(
            organization=self.organization, conversation=self.conversation,
            author_type="OPERATOR", author_user=self.user, text="Existing public reply",
        )
        self.assertEqual(self.scheduled().responder_ids, [self.user.pk])

    def test_foreign_relations_duplicate_and_mutation_rejected_by_database(self):
        target = self.scheduled()
        for changes in ({"conversation_id": self.foreign_conversation.pk},
                        {"organization_id": self.foreign.pk}):
            row = RatingRequest(
                organization=self.organization, conversation=self.conversation,
                completion=target.completion, scale=self.scale, text="Question", delay_seconds=0,
                due_at=timezone.now(),
            )
            for name, value in changes.items():
                setattr(row, name, value)
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError):
                    row.save()
                with self.assertRaises(DatabaseError), transaction.atomic():
                    RatingRequest.objects.bulk_create([row])
        for changes in ({"scale": []}, {"responder_ids": [self.foreign_user.pk]},
                        {"conversation_id": self.foreign_conversation.pk}, {"text": "Replacement"}):
            with self.subTest(changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                RatingRequest.objects.filter(pk=target.pk).update(**changes)
        with self.assertRaises(DatabaseError), transaction.atomic():
            RatingRequest.objects.bulk_create([RatingRequest(
                organization=self.organization, conversation=self.conversation, completion=target.completion,
                scale=self.scale, text="Question", delay_seconds=0, due_at=timezone.now(),
            )])

    def test_result_is_unique_immutable_and_bound_to_snapshot(self):
        target = self.scheduled()
        deliver_due_requests(self.context)
        target.refresh_from_db()
        with self.assertRaises(DatabaseError), transaction.atomic():
            CustomerRating.objects.bulk_create([CustomerRating(
                organization=self.organization, request=target, value="6",
            )])
        rating = CustomerRating.objects.create(organization=self.organization, request=target, value="5")
        for changes in ({"value": "1"}, {"comment": "Changed"}, {"organization_id": self.foreign.pk}):
            with self.subTest(changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                CustomerRating.objects.filter(pk=rating.pk).update(**changes)
        with self.assertRaises(DatabaseError), transaction.atomic():
            CustomerRating.objects.create(organization=self.organization, request=target, value="5")
        with self.assertRaises(DatabaseError), transaction.atomic():
            CustomerRating.objects.bulk_create([CustomerRating(
                organization=self.foreign, request=target, value="5",
            )])
        for changes in ({"credential_hash": "x" * 64}, {"expires_at": timezone.now() + timedelta(days=100)}):
            with self.subTest(changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                RatingRequest.objects.filter(pk=target.pk).update(**changes)

    def test_forced_rls_denies_runtime_without_context_and_foreign_tenant(self):
        target = self.scheduled()
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            self.assertEqual(RatingRequest.objects.count(), 0)
            self.assertEqual(RatingSettings.objects.count(), 0)
        with tenant_atomic(self.context), connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            self.assertEqual(list(RatingRequest.objects.values_list("pk", flat=True)), [target.pk])
            self.assertFalse(RatingSettings.objects.filter(organization=self.foreign).exists())
            with self.assertRaises(DatabaseError), transaction.atomic():
                RatingSettings.objects.create(organization=self.foreign)
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE NONE")
            for model in (RatingSettings, RatingRequest, CustomerRating):
                cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=%s",
                               [model._meta.db_table])
                self.assertEqual(cursor.fetchone(), (True, True))
                cursor.execute("SELECT has_table_privilege('chatballs_runtime_platform', %s, 'SELECT')",
                               [model._meta.db_table])
                self.assertFalse(cursor.fetchone()[0])
