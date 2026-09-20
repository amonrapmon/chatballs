from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from chatballs.events.handlers import dispatch, register


class EventHandlerRegistryTests(SimpleTestCase):
    def test_registration_defaults_to_tenant_atomic(self) -> None:
        @register("tests.legacy-defaults")
        def handler(payload: dict, context) -> None:  # noqa: ANN001
            return None

        event = SimpleNamespace(event_type="tests.legacy-defaults", payload={})
        context = object()
        with (
            mock.patch("chatballs.events.handlers.tenant_context_for_event", return_value=context),
            mock.patch("chatballs.events.handlers.tenant_atomic") as tenant_atomic,
        ):
            dispatch(event)

        tenant_atomic.assert_called_once_with(context)

    def test_handler_managing_own_transaction_is_dispatched_without_tenant_atomic(self) -> None:
        observed: list[object] = []

        @register("tests.own-transaction", manages_own_transaction=True)
        def handler(payload: dict, context) -> None:  # noqa: ANN001
            observed.append(context)

        event = SimpleNamespace(event_type="tests.own-transaction", payload={})
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
