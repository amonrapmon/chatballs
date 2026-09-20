from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from chatballs.events.handlers import dispatch, get_registration, register


class EventHandlerRegistryTests(SimpleTestCase):
    def test_legacy_registration_keeps_transactional_defaults(self) -> None:
        @register("tests.legacy-defaults")
        def handler(payload: dict, context) -> None:  # noqa: ANN001
            return None

        registration = get_registration("tests.legacy-defaults")

        self.assertIsNotNone(registration)
        self.assertIs(registration.handler, handler)
        self.assertTrue(registration.tenant_transaction)
        self.assertFalse(registration.recover_stale_processing)

    def test_non_transactional_handler_is_dispatched_without_tenant_atomic(self) -> None:
        observed: list[object] = []

        @register("tests.non-transactional", tenant_transaction=False)
        def handler(payload: dict, context) -> None:  # noqa: ANN001
            observed.append(context)

        event = SimpleNamespace(event_type="tests.non-transactional", payload={})
        context = object()
        with (
            mock.patch("chatballs.events.handlers.tenant_context_for_event", return_value=context),
            mock.patch("chatballs.events.handlers.tenant_atomic") as tenant_atomic,
        ):
            dispatch(event)

        self.assertEqual(observed, [context])
        tenant_atomic.assert_not_called()

    def test_legacy_handler_is_dispatched_inside_tenant_atomic(self) -> None:
        @register("tests.transactional")
        def handler(payload: dict, context) -> None:  # noqa: ANN001
            return None

        event = SimpleNamespace(event_type="tests.transactional", payload={})
        context = object()
        with (
            mock.patch("chatballs.events.handlers.tenant_context_for_event", return_value=context),
            mock.patch("chatballs.events.handlers.tenant_atomic") as tenant_atomic,
        ):
            dispatch(event)

        tenant_atomic.assert_called_once_with(context)
        tenant_atomic.return_value.__enter__.assert_called_once_with()
        tenant_atomic.return_value.__exit__.assert_called_once()
