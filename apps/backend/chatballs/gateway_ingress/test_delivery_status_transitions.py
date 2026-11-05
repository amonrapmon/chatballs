from .test_delivery_status import GatewayDeliveryStatusTests


class GatewayDeliveryStatusTransitionTests(GatewayDeliveryStatusTests):
    def test_monotonic_transitions_and_failure_metadata(self) -> None:
        message = self._message()
        self.assertEqual(self._post(self._payload(message)).status_code, 202)
        self.assertEqual(
            self._post(
                self._payload(
                    message,
                    status="failed",
                    external_message_id="provider-message-1",
                    failure_kind="provider_failed",
                )
            ).status_code,
            202,
        )
        message.refresh_from_db()
        self.assertEqual(message.delivery_status, "failed")
        self.assertEqual(message.delivery_failure_kind, "provider_failed")
        self.assertEqual(
            self._post(
                self._payload(
                    message,
                    status="delivered",
                    external_message_id="provider-message-1",
                )
            ).status_code,
            202,
        )
        self.assertEqual(
            self._post(
                self._payload(
                    message,
                    status="read",
                    external_message_id="provider-message-1",
                )
            ).status_code,
            202,
        )
        message.refresh_from_db()
        read_timestamp = message.delivery_status_at
        self.assertEqual(message.delivery_status, "read")
        self.assertEqual(message.delivery_failure_kind, "")
        self.assertEqual(
            self._post(
                self._payload(
                    message,
                    status="delivered",
                    external_message_id="provider-message-1",
                )
            ).status_code,
            202,
        )
        self.assertEqual(
            self._post(
                self._payload(
                    message,
                    status="failed",
                    external_message_id="provider-message-1",
                    failure_kind="provider_failed",
                )
            ).status_code,
            202,
        )
        message.refresh_from_db()
        self.assertEqual(message.delivery_status, "read")
        self.assertEqual(message.delivery_status_at, read_timestamp)

        duplicate = self._message()
        self.assertEqual(self._post(self._payload(duplicate)).status_code, 202)
        self.assertEqual(
            self._post(
                self._payload(
                    duplicate,
                    status="delivered",
                    occurred_at="2026-09-20T12:35:00Z",
                )
            ).status_code,
            202,
        )
        duplicate.refresh_from_db()
        delivered_timestamp = duplicate.delivery_status_at
        self.assertEqual(
            self._post(
                self._payload(
                    duplicate,
                    status="delivered",
                    occurred_at="2026-09-20T12:36:00Z",
                )
            ).status_code,
            202,
        )
        duplicate.refresh_from_db()
        self.assertEqual(duplicate.delivery_status_at, delivered_timestamp)
        self.assertEqual(
            self._post(
                self._payload(
                    duplicate,
                    status="read",
                    occurred_at="2026-09-20T12:37:00Z",
                )
            ).status_code,
            202,
        )
        duplicate.refresh_from_db()
        read_timestamp = duplicate.delivery_status_at
        self.assertEqual(
            self._post(
                self._payload(
                    duplicate,
                    status="read",
                    occurred_at="2026-09-20T12:38:00Z",
                )
            ).status_code,
            202,
        )
        duplicate.refresh_from_db()
        self.assertEqual(duplicate.delivery_status_at, read_timestamp)

        failed = self._message()
        self.assertEqual(
            self._post(
                self._payload(
                    failed,
                    status="failed",
                    external_message_id=None,
                    failure_kind="provider_failed",
                )
            ).status_code,
            202,
        )
        failed.refresh_from_db()
        self.assertEqual(failed.delivery_failure_kind, "provider_failed")
        self.assertEqual(
            self._post(
                self._payload(
                    failed,
                    status="delivered",
                    external_message_id="provider-recovered",
                )
            ).status_code,
            202,
        )
        failed.refresh_from_db()
        self.assertEqual(failed.delivery_status, "delivered")
        self.assertEqual(failed.delivery_failure_kind, "")

        failed_to_read = self._message()
        self.assertEqual(
            self._post(
                self._payload(
                    failed_to_read,
                    status="failed",
                    external_message_id=None,
                    failure_kind="provider_failed",
                )
            ).status_code,
            202,
        )
        self.assertEqual(
            self._post(
                self._payload(
                    failed_to_read,
                    status="read",
                    external_message_id="provider-read-after-failure",
                )
            ).status_code,
            202,
        )
        failed_to_read.refresh_from_db()
        self.assertEqual(failed_to_read.delivery_status, "read")
        self.assertEqual(failed_to_read.delivery_failure_kind, "")

        no_account = self._message()
        self.assertEqual(
            self._post(
                self._payload(
                    no_account,
                    status="no_account",
                    external_message_id=None,
                    failure_kind="no_account",
                )
            ).status_code,
            202,
        )
        no_account.refresh_from_db()
        self.assertEqual(no_account.delivery_failure_kind, "no_account")
        accepted_to_no_account = self._message()
        self.assertEqual(
            self._post(self._payload(accepted_to_no_account)).status_code,
            202,
        )
        self.assertEqual(
            self._post(
                self._payload(
                    accepted_to_no_account,
                    status="no_account",
                    external_message_id="provider-message-1",
                    failure_kind="no_account",
                )
            ).status_code,
            202,
        )
        accepted_to_no_account.refresh_from_db()
        self.assertEqual(accepted_to_no_account.delivery_status, "no_account")
        self.assertEqual(
            self._post(
                self._payload(
                    no_account,
                    status="read",
                    external_message_id="provider-no-account-recovered",
                )
            ).status_code,
            202,
        )
        no_account.refresh_from_db()
        self.assertEqual(no_account.delivery_status, "read")
        self.assertEqual(no_account.delivery_failure_kind, "")

        no_account_to_delivered = self._message()
        self.assertEqual(
            self._post(
                self._payload(
                    no_account_to_delivered,
                    status="no_account",
                    external_message_id=None,
                    failure_kind="no_account",
                )
            ).status_code,
            202,
        )
        self.assertEqual(
            self._post(
                self._payload(
                    no_account_to_delivered,
                    status="delivered",
                    external_message_id="provider-delivered-after-no-account",
                )
            ).status_code,
            202,
        )
        no_account_to_delivered.refresh_from_db()
        self.assertEqual(no_account_to_delivered.delivery_status, "delivered")
        self.assertEqual(no_account_to_delivered.delivery_failure_kind, "")
