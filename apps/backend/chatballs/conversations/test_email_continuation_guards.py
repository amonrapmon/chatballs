from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction

from chatballs.channels.models import Channel
from chatballs.conversations.email_attempt_models import (
    EmailSendAttempt,
    EmailSendOperation,
)
from chatballs.conversations.email_continuation_test_base import (
    EmailContinuationTestBase,
)
from chatballs.conversations.email_thread_models import EmailThread, EmailThreadMessage
from chatballs.conversations.models import Contact, Conversation, Message
from chatballs.events.models import OutboxEvent
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic

MODELS = (EmailThread, EmailThreadMessage, EmailSendOperation, EmailSendAttempt)


class EmailContinuationGuardTests(EmailContinuationTestBase):
    def foreign_rows(self):
        channel = Channel.objects.create(organization=self.foreign, name="Foreign", code="foreign")
        web = self.make_connection(self.foreign, "WEB", "Foreign web", channel)
        contact = Contact.objects.create(organization=self.foreign, email=self.contact.email)
        conversation = Conversation.objects.create(
            organization=self.foreign, channel=channel, connection=web, contact=contact,
        )
        thread = self.thread(organization=self.foreign, conversation=conversation, connection=self.foreign_mailbox)
        thread.save()
        letter = self.letter(thread)
        letter.save()
        operation = EmailSendOperation.objects.create(letter=letter, initiated_by=self.foreign_member, client_key="foreign")
        event = OutboxEvent.objects.create(
            ownership="TENANT", organization=self.foreign, event_type="conversations.email_send_requested",
            aggregate_type="email_operation", aggregate_id=str(operation.pk),
        )
        attempt = EmailSendAttempt.objects.create(
            operation=operation, number=1, initiated_by=self.foreign_member, outbox_event=event,
        )
        return thread, letter, operation, attempt

    @staticmethod
    def app_role():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE chatballs_runtime_app")

    def test_every_relation_has_model_and_database_tenant_protection(self):
        foreign_thread, foreign_letter, foreign_operation, foreign_attempt = self.foreign_rows()
        unused_message = Message.objects.create(conversation=foreign_thread.conversation, author_type="OPERATOR")
        unused_letter = self.letter(foreign_thread)
        unused_letter.save()
        unused_event = OutboxEvent.objects.create(
            ownership="TENANT", organization=self.foreign, event_type="conversations.email_send_requested",
            aggregate_type="email_operation", aggregate_id=str(foreign_operation.pk),
        )

        def operation_row():
            row = self.operation()
            row.delete()
            return row

        def attempt_row():
            return self.attempt(self.operation(), number=77, organization=self.organization)

        factories = (
            lambda: self.thread(),
            lambda: self.letter(self.operation().letter.thread),
            operation_row,
            attempt_row,
        )
        foreign_relations = (
            {"conversation": foreign_thread.conversation, "connection": self.foreign_mailbox},
            {"thread": foreign_thread, "connection": self.foreign_mailbox, "message": unused_message},
            {"letter": unused_letter, "initiated_by": self.foreign_member},
            {"operation": foreign_operation, "initiated_by": self.foreign_member,
             "outbox_event": unused_event},
        )
        for model, factory, relations in zip(MODELS, factories, foreign_relations, strict=True):
            for field, value in {"organization": self.foreign, **relations}.items():
                with self.subTest(model=model.__name__, field=field):
                    row = factory()
                    setattr(row, field, value)
                    with self.assertRaises(ValidationError):
                        row.validate_tenant_relations()
                    with self.assertRaisesMessage(DatabaseError, "cross-tenant relation"), transaction.atomic():
                        model.objects.bulk_create([row])
            saved = {EmailThread: foreign_thread, EmailThreadMessage: foreign_letter,
                     EmailSendOperation: foreign_operation, EmailSendAttempt: foreign_attempt}[model]
            with self.assertRaisesMessage(DatabaseError, "cross-tenant relation"), transaction.atomic():
                model.objects.filter(pk=saved.pk).update(organization_id=self.organization.pk)

    def test_rls_hides_all_mail_data_without_context_and_from_other_tenant(self):
        operation = self.operation()
        attempt = self.attempt(operation)
        attempt.save()
        rows = (operation.letter.thread, operation.letter, operation, attempt)
        foreign_context = TenantContext.for_membership(self.foreign_member)
        with transaction.atomic():
            self.app_role()
            for model in MODELS:
                self.assertEqual(model.objects.count(), 0)
            with self.assertRaises(DatabaseError), transaction.atomic():
                EmailThread.objects.bulk_create([self.thread()])
        with tenant_atomic(foreign_context):
            self.app_role()
            for model, row in zip(MODELS, rows, strict=True):
                self.assertEqual(model.objects.count(), 0)
                self.assertEqual(model.objects.filter(pk=row.pk).update(organization_id=self.foreign.pk), 0)
            with self.assertRaises(DatabaseError), transaction.atomic():
                EmailThread.objects.bulk_create([self.thread()])
        with tenant_atomic(self.context):
            self.app_role()
            for model, row in zip(MODELS, rows, strict=True):
                self.assertEqual(list(model.objects.values_list("pk", flat=True)), [row.pk])
            new_operation = self.operation()
            new_attempt = self.attempt(new_operation)
            new_attempt.save()
            self.assertEqual(EmailSendAttempt.objects.count(), 2)

    def test_database_rejects_invalid_routing_even_inside_one_tenant(self):
        operation = self.operation()
        letter = operation.letter
        thread = letter.thread
        other_conversation = Conversation.objects.create(organization=self.organization, channel=self.channel, contact=self.contact)
        other_message = Message.objects.create(conversation=other_conversation, author_type="OPERATOR")
        self.other_mailbox.is_active = False
        self.other_mailbox.save(update_fields=["is_active"])
        for changes in (
            {"connection": self.web}, {"recipient": "stranger@example.test"}, {"subject": ""},
            {"connection": self.other_mailbox}, {"conversation": other_conversation},
        ):
            with self.subTest(changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                EmailThread.objects.bulk_create([self.thread(**changes)])
        for changes in ({"connection": self.other_mailbox}, {"message": other_message}):
            with self.subTest(changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                EmailThreadMessage.objects.bulk_create([self.letter(thread, **changes)])
        inbound = self.letter(thread, direction="INBOUND")
        inbound.save()
        with self.assertRaises(DatabaseError), transaction.atomic():
            EmailSendOperation.objects.bulk_create([
                EmailSendOperation(organization=self.organization, letter=inbound, initiated_by=self.member, client_key="inbound"),
            ])
        platform_event = OutboxEvent.objects.create(
            event_type="platform.noop", aggregate_type="platform", aggregate_id="1",
        )
        with self.assertRaisesMessage(DatabaseError, "cross-tenant relation"), transaction.atomic():
            EmailSendAttempt.objects.bulk_create([
                self.attempt(operation, outbox_event=platform_event, organization=self.organization),
            ])

    def test_selected_transport_and_operation_snapshot_cannot_be_replaced(self):
        operation = self.operation()
        attempt = self.attempt(operation)
        attempt.save()
        other_operation = self.operation()
        other_attempt = self.attempt(other_operation)
        other_attempt.save()
        for row, changes in (
            (operation.letter.thread, {"connection_id": self.other_mailbox.pk}),
            (operation.letter.thread, {"recipient": "another@example.test"}),
            (operation.letter, {"mail_message_id": "<replacement@example.test>"}),
            (operation, {"letter_id": other_operation.letter_id}),
            (attempt, {"operation_id": other_operation.pk}),
            (attempt, {"outbox_event_id": other_attempt.outbox_event_id}),
        ):
            with self.subTest(model=type(row).__name__, changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                type(row).objects.filter(pk=row.pk).update(**changes)

    def test_database_security_configuration(self):
        with connection.cursor() as cursor:
            for model in MODELS:
                table = model._meta.db_table
                cursor.execute(
                    "SELECT relrowsecurity, relforcerowsecurity, pg_get_userbyid(relowner) FROM pg_class WHERE relname = %s",
                    [table],
                )
                self.assertEqual(cursor.fetchone(), (True, True, "chatballs_schema"))
                cursor.execute("SELECT has_table_privilege('chatballs_runtime_platform', %s, 'SELECT')", [table])
                self.assertFalse(cursor.fetchone()[0])
