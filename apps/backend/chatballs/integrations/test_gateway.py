from unittest import mock

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from chatballs.conversations import transports
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import Organization
from chatballs.integrations import checks
from chatballs.integrations.models import (
    Integration,
    IntegrationKind,
    IntegrationProvider,
    IntegrationStatus,
)
from chatballs.integrations.serializers import integration_payload
from chatballs.integrations.services import (
    IntegrationInput,
    create_integration,
)
from chatballs.integrations.services import test_integration as run_integration_test
from chatballs.testing import system_tenant_context


class GatewayIntegrationTests(TestCase):
    def setUp(self) -> None:
        bootstrap_owner(email="owner@example.com", password="temporary-password")
        self.context = system_tenant_context(Organization.objects.get(slug="demo"))

    def _create(self, *, secret="gateway-secret", config=None):
        return create_integration(
            context=self.context,
            data=IntegrationInput(
                provider=IntegrationProvider.GATEWAY,
                name="Gateway source",
                secret=secret,
                config=config
                or {"sourceId": " tg-studio-main ", "baseUrl": " https://gateway.example.test/ "},
            ),
        )

    def test_gateway_is_messenger_and_normalizes_source_and_base_url(self) -> None:
        integration = self._create()

        self.assertEqual(integration.kind, IntegrationKind.MESSENGER)
        self.assertEqual(
            integration.config,
            {"source_id": "tg-studio-main", "base_url": "https://gateway.example.test/"},
        )
        self.assertEqual(integration.secret, "gateway-secret")

    def test_gateway_requires_secret_and_source_id(self) -> None:
        with self.assertRaises(ValidationError):
            self._create(secret="")
        with self.assertRaises(ValidationError):
            self._create(config={"baseUrl": "https://gateway.example.test"})
        with self.assertRaises(ValidationError):
            self._create(config={"sourceId": "tg-studio-main"})

    def test_gateway_serializer_exposes_config_but_not_secret(self) -> None:
        integration = self._create()

        payload = integration_payload(integration)

        self.assertEqual(payload["config"]["sourceId"], "tg-studio-main")
        self.assertEqual(payload["config"]["baseUrl"], "https://gateway.example.test/")
        self.assertNotIn("gateway-secret", str(payload))

    def test_non_gateway_serializer_does_not_expose_gateway_source_id(self) -> None:
        integration = Integration.objects.create(
            organization=self.context.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.TELEGRAM,
            name="Telegram source",
            secret="telegram-secret",
            config={"base_url": "https://telegram.example.test/"},
        )

        payload = integration_payload(integration)

        self.assertNotIn("sourceId", payload["config"])

    def test_gateway_health_check_dispatches_secret_and_base_url(self) -> None:
        integration = self._create(secret="wrong-secret")

        with mock.patch.object(
            checks,
            "check_gateway",
            return_value=(True, "gateway available", {}),
        ) as check:
            checked = run_integration_test(context=self.context, integration=integration)

        check.assert_called_once_with(
            secret="wrong-secret",
            base_url="https://gateway.example.test/",
        )
        self.assertEqual(checked.status, IntegrationStatus.OK)


class GatewayHealthCheckTests(SimpleTestCase):
    def test_healthy_endpoint_is_success_even_when_secret_is_not_validated(self) -> None:
        with mock.patch.object(checks, "_get", return_value=(200, {"ok": True})) as get:
            ok, _detail, meta = checks.check_gateway(
                secret="not-validated",
                base_url="https://gateway.example.test/",
            )

        self.assertTrue(ok)
        self.assertEqual(meta, {})
        get.assert_called_once_with(
            "https://gateway.example.test/healthz",
            headers={"Authorization": "Bearer not-validated"},
        )

    def test_non_healthy_endpoint_is_failure(self) -> None:
        with mock.patch.object(checks, "_get", return_value=(200, {"ok": False})):
            ok, _detail, _meta = checks.check_gateway(
                secret="not-validated",
                base_url="https://gateway.example.test",
            )

        self.assertFalse(ok)

    def test_malformed_health_response_is_failure(self) -> None:
        with mock.patch.object(checks, "_get", return_value=(200, [])):
            ok, _detail, _meta = checks.check_gateway(
                secret="not-validated",
                base_url="https://gateway.example.test",
            )

        self.assertFalse(ok)

    def test_gateway_is_not_registered_for_polling(self) -> None:
        self.assertNotIn(IntegrationProvider.GATEWAY, transports._POLL)
        self.assertNotIn(IntegrationProvider.GATEWAY, transports.SUPPORTED_PROVIDERS)
