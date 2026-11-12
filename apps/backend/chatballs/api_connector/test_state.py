"""GEN-195: Integration remains the authority for an external adapter's runtime."""

from django.test import TestCase
from django.urls import reverse

from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.testing import TenantAPIClient, system_tenant_context


class ConnectorRuntimeStateTests(TestCase):
    def setUp(self):
        result = bootstrap_owner(
            email="connector-state-owner@example.com",
            password="Temporary-Password-2026!",
        )
        self.org = result.organization
        self.client = TenantAPIClient()
        self.client.force_login(result.owner)
        self.integration = create_integration(
            context=system_tenant_context(self.org),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR,
                name="External Telegram",
                config={"connectorService": "green_api_telegram"},
            ),
        )
        self.path = reverse("api-connector-runtime-state", kwargs={
            "connector_organization_public_id": self.org.public_id,
            "integration_id": self.integration.id,
        })
        response = self.client.post(
            f"/api/v1/integrations/{self.integration.id}/connector-credential/",
            data={}, format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.token = response.data["token"]

    def state(self, token=None):
        return self.client.get(
            self.path, HTTP_AUTHORIZATION=f"Bearer {self.token if token is None else token}",
        )

    def test_authorized_state_has_no_secrets_and_tracks_integration(self):
        response = self.state()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["sourceId"], f"connection-{self.integration.id}")
        self.assertEqual(response.data["connectorService"], "green_api_telegram")
        self.assertTrue(response.data["active"])
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertNotIn(self.token, str(response.data))
        self.assertNotIn("secret", str(response.data))

        self.integration.is_active = False
        self.integration.save(update_fields=["is_active"])
        self.assertIs(self.state().data["active"], False)

        self.integration.is_active = True
        self.integration.save(update_fields=["is_active"])
        self.integration.channel.is_active = False
        self.integration.channel.save(update_fields=["is_active"])
        self.assertIs(self.state().data["active"], False)

    def test_rotated_token_revokes_previous_and_invalid_token_is_denied(self):
        self.assertEqual(self.state(token="wrong-token").status_code, 401)
        old = self.token
        response = self.client.post(
            f"/api/v1/integrations/{self.integration.id}/connector-credential/",
            data={}, format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.token = response.data["token"]
        self.assertEqual(self.state(token=old).status_code, 401)
        self.assertEqual(self.state().status_code, 200)
