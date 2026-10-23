"""Connector service choice is metadata, not active provider authorization."""

from django.test import TestCase

from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import IntegrationKind, IntegrationProvider
from chatballs.integrations.serializers import integration_payload
from chatballs.integrations.services import IntegrationInput, create_integration, update_integration
from chatballs.testing import system_tenant_context


class APIConnectorProfileTests(TestCase):
    def setUp(self):
        self.owner = bootstrap_owner(
            email="connector-profile-owner@example.com", password="Temporary-Test-Password!",
        )
        self.context = system_tenant_context(self.owner.organization)

    def test_profile_is_stored_and_exposed_without_credentials(self):
        connection = create_integration(
            context=self.context,
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR,
                name="MAX через Green API",
                config={"connectorService": "green_api_max", "apiTokenInstance": "must-not-persist"},
            ),
        )
        self.assertEqual(connection.kind, IntegrationKind.MESSENGER)
        self.assertEqual(connection.config, {"connector_service": "green_api_max"})
        self.assertEqual(connection.secret, "")
        self.assertIsNotNone(connection.channel_id)
        payload = integration_payload(connection)
        self.assertEqual(payload["config"]["connectorService"], "green_api_max")
        self.assertNotIn("apiTokenInstance", str(payload))

    def test_profile_is_editable(self):
        connection = create_integration(
            context=self.context,
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR,
                name="Канал",
                config={"connectorService": "green_api_max"},
            ),
        )
        connection = update_integration(
            context=self.context, integration=connection,
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR,
                name="Канал",
                config={"connectorService": "green_api_telegram"},
                channel_id=connection.channel_id,
            ),
        )
        self.assertEqual(connection.config, {"connector_service": "green_api_telegram"})

    def test_invalid_service_identifier_is_rejected(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            create_integration(
                context=self.context,
                data=IntegrationInput(
                    provider=IntegrationProvider.API_CONNECTOR,
                    name="Неверный канал",
                    config={"connectorService": "../../invalid"},
                ),
            )
