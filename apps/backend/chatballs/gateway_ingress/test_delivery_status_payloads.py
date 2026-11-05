from datetime import UTC, datetime
from uuid import UUID

from django.test import SimpleTestCase

from chatballs.gateway_ingress.payloads import (
    GatewayPayloadError,
    UnsupportedGatewayDeliveryStatusError,
    parse_delivery_status_payload,
)


def _payload(**overrides: object) -> dict:
    payload = {
        "schema": "intercom-gw.chatballs.delivery-status.v1",
        "source_id": "tg-studio-main",
        "command_id": "550e8400-e29b-41d4-a716-446655440000",
        "external_chat_id": "79991234567@c.us",
        "external_message_id": "BAE5-message",
        "status": "delivered",
        "occurred_at": "2026-09-20T12:34:56Z",
        "failure_kind": None,
    }
    payload.update(overrides)
    return payload


class GatewayDeliveryStatusPayloadTests(SimpleTestCase):
    def test_parser_returns_typed_delivery_status_payload(self) -> None:
        parsed = parse_delivery_status_payload(_payload())

        self.assertEqual(parsed.source_id, "tg-studio-main")
        self.assertEqual(
            parsed.command_id,
            UUID("550e8400-e29b-41d4-a716-446655440000"),
        )
        self.assertEqual(parsed.external_chat_id, "79991234567@c.us")
        self.assertEqual(parsed.external_message_id, "BAE5-message")
        self.assertEqual(parsed.status, "delivered")
        self.assertEqual(
            parsed.occurred_at,
            datetime(2026, 9, 20, 12, 34, 56, tzinfo=UTC),
        )

    def test_failure_status_allows_null_provider_id_and_safe_failure_kind(self) -> None:
        parsed = parse_delivery_status_payload(
            _payload(
                external_message_id=None,
                status="failed",
                failure_kind="provider_failed",
            )
        )

        self.assertIsNone(parsed.external_message_id)
        self.assertEqual(parsed.failure_kind, "provider_failed")

    def test_missing_occurred_at_is_left_for_receipt_time_fallback(self) -> None:
        parsed = parse_delivery_status_payload(_payload(occurred_at=None))

        self.assertIsNone(parsed.occurred_at)

    def test_positive_status_requires_non_empty_provider_id(self) -> None:
        for status in ("provider_accepted", "delivered", "read"):
            with self.subTest(status=status):
                with self.assertRaises(GatewayPayloadError):
                    parse_delivery_status_payload(
                        _payload(status=status, external_message_id=None)
                    )

    def test_unsupported_status_is_distinguished_from_malformed_payload(self) -> None:
        with self.assertRaises(UnsupportedGatewayDeliveryStatusError):
            parse_delivery_status_payload(_payload(status="queued"))

    def test_rejects_invalid_failure_kind_and_non_utc_timestamp(self) -> None:
        with self.assertRaises(GatewayPayloadError):
            parse_delivery_status_payload(_payload(failure_kind="provider_secret"))
        with self.assertRaises(GatewayPayloadError):
            parse_delivery_status_payload(_payload(occurred_at="2026-09-20T12:34:56"))
