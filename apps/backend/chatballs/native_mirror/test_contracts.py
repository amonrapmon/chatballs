"""Pure domain tests: no database, credentials, transport or network required."""

from datetime import datetime, timezone

from django.test import SimpleTestCase

from chatballs.native_mirror.classification import (
    OriginClass,
    VerifiedEvidence,
    classify_origin,
)
from chatballs.native_mirror.contracts import NativeReplyEvent
from chatballs.native_mirror.policy import MirrorMode, mode_for_config


class MirrorContractsTests(SimpleTestCase):
    def event(self, **overrides):
        values = dict(
            integration_id=123,
            provider="GATEWAY",
            source_id="tg-main",
            external_chat_id="chat-1",
            event_id="event-7",
            external_message_id="msg-7",
            occurred_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
            text="Ответ из нативного приложения",
        )
        values.update(overrides)
        return NativeReplyEvent(**values)

    def test_dedup_is_scoped_to_integration_and_event_id(self):
        one = self.event()
        second = self.event(integration_id=321)
        self.assertEqual(one.dedup_key, (123, "event-7"))
        self.assertNotEqual(one.dedup_key, second.dedup_key)

    def test_equal_message_text_does_not_imply_duplicate_event(self):
        self.assertNotEqual(
            self.event(event_id="event-1").dedup_key,
            self.event(event_id="event-2").dedup_key,
        )

    def test_blank_routing_and_identifier_fields_are_rejected(self):
        for field in ("provider", "source_id", "external_chat_id",
                      "event_id", "external_message_id", "text"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.event(**{field: "  "})

    def test_invalid_integration_id_is_rejected(self):
        for integration_id in (0, -1, True, "123"):
            with self.subTest(value=integration_id), self.assertRaises(ValueError):
                self.event(integration_id=integration_id)

    def test_naive_datetime_is_rejected(self):
        with self.assertRaises(ValueError):
            self.event(occurred_at=datetime(2026, 10, 12))

    def test_unknown_or_missing_mode_preserves_legacy(self):
        for config in (None, {}, {"native_mirror_mode": "ENABLED "},
                       {"native_mirror_mode": "enabled"},
                       {"native_mirror_mode": True}, {"native_mirror_mode": "OTHER"}):
            with self.subTest(config=config):
                self.assertEqual(mode_for_config(config), MirrorMode.LEGACY)

    def test_all_explicit_modes(self):
        for mode in MirrorMode:
            with self.subTest(mode=mode):
                self.assertEqual(
                    mode_for_config({"native_mirror_mode": mode.value}), mode
                )

    def test_unknown_author_is_never_authorized(self):
        self.assertEqual(
            classify_origin(VerifiedEvidence(source_authenticated=True)),
            OriginClass.EXTERNAL_UNCLASSIFIED,
        )

    def test_unverified_source_cannot_authorize_actor(self):
        self.assertEqual(
            classify_origin(VerifiedEvidence(staff_membership_verified=True)),
            OriginClass.EXTERNAL_UNCLASSIFIED,
        )

    def test_positive_correlated_self_echo(self):
        self.assertEqual(
            classify_origin(VerifiedEvidence(
                source_authenticated=True, own_outbound_correlated=True
            )),
            OriginClass.SELF_ECHO,
        )

    def test_verified_staff_requires_authenticated_source(self):
        self.assertEqual(
            classify_origin(VerifiedEvidence(
                source_authenticated=True, staff_membership_verified=True
            )),
            OriginClass.EXTERNAL_AUTHORIZED,
        )

    def test_conflicting_evidence_is_not_treated_as_human(self):
        self.assertEqual(
            classify_origin(VerifiedEvidence(
                source_authenticated=True,
                own_outbound_correlated=True,
                staff_membership_verified=True,
            )),
            OriginClass.EXTERNAL_UNCLASSIFIED,
        )
