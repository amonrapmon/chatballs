from unittest import mock

from django.test import TestCase

from chatballs.ai.models import AIAgent
from chatballs.channels.models import Channel
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import AuditEvent, Organization
from chatballs.integrations import checking
from chatballs.integrations.models import Integration, IntegrationProvider
from chatballs.integrations.services import (
    IntegrationInput,
    create_integration,
    test_integration,
    update_integration,
)
from chatballs.testing import system_tenant_context


def custom_input(*, name: str = "Мой провайдер", secret: str | None = "sk-custom", base_url: str = "https://api.example/v1") -> IntegrationInput:
    return IntegrationInput(
        provider=IntegrationProvider.CUSTOM,
        name=name,
        secret=secret,
        config={"baseUrl": base_url, "defaultModel": "model"},
    )


class ProviderRuntimeRevisionTests(TestCase):
    def setUp(self) -> None:
        bootstrap_owner(email="owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.context = system_tenant_context(self.organization)

    def test_runtime_change_advances_revision_but_rename_does_not(self) -> None:
        integration = create_integration(context=self.context, data=custom_input(secret="sk-old"))
        initial_revision = integration.runtime_revision

        renamed = update_integration(
            context=self.context,
            integration=integration,
            data=custom_input(
                name="Новое имя",
                secret=None,
            ),
        )
        self.assertEqual(renamed.runtime_revision, initial_revision)

        updated = update_integration(
            context=self.context,
            integration=renamed,
            data=custom_input(name=renamed.name, secret="sk-new", base_url="https://new.example/v1"),
        )
        self.assertEqual(updated.runtime_revision, initial_revision + 1)

    def test_successful_check_advances_runtime_revision(self) -> None:
        integration = create_integration(context=self.context, data=custom_input())
        initial_revision = integration.runtime_revision
        with mock.patch.dict(
            checking._CHECKS,
            {IntegrationProvider.CUSTOM: lambda **_kwargs: (True, "ok", {})},
        ):
            checked = test_integration(context=self.context, integration=integration)

        self.assertEqual(checked.runtime_revision, initial_revision + 1)


class IntegrationDeletionTests(TestCase):
    def setUp(self) -> None:
        bootstrap_owner(email="owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.context = system_tenant_context(self.organization)
        self.client.login(username="owner@example.com", password="temporary-password")

    def _url(self, integration_id: int) -> str:
        return f"/api/v1/organizations/{self.organization.public_id}/integrations/{integration_id}/"

    def test_used_provider_returns_conflict_and_is_not_audited_as_deleted(self) -> None:
        integration = create_integration(context=self.context, data=custom_input())
        channel = Channel.objects.create(
            organization=self.organization,
            code="protected-provider",
            name="Канал",
        )
        AIAgent.objects.create(
            channel=channel,
            name="Агент",
            provider_integration=integration,
        )

        response = self.client.delete(self._url(integration.id))

        self.assertEqual(response.status_code, 409)
        self.assertIn("используется", response.json()["detail"])
        self.assertTrue(Integration.objects.filter(id=integration.id).exists())
        self.assertFalse(
            AuditEvent.objects.filter(
                action="integrations.integration_deleted",
                object_id=str(integration.id),
            ).exists()
        )

    def test_unused_provider_is_deleted_and_audited_with_original_id(self) -> None:
        integration = create_integration(
            context=self.context,
            data=custom_input(name="Свободный провайдер"),
        )
        integration_id = integration.id

        response = self.client.delete(self._url(integration_id))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Integration.objects.filter(id=integration_id).exists())
        self.assertTrue(
            AuditEvent.objects.filter(
                action="integrations.integration_deleted",
                object_id=str(integration_id),
            ).exists()
        )
