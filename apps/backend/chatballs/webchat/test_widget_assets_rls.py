"""Иконки виджета под реальной ролью backend-app: RLS, триггеры и каталог входа.

Обычные тесты ходят в базу ролью-владельцем схемы, для которой RLS открыта.
Здесь запросы идут ролью ``chatballs_runtime_app``, как в production.
"""

from __future__ import annotations

from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from chatballs.channels.models import Channel
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import EmployeeRole, HumanUser, Organization, OrganizationMembership
from chatballs.tenancy import storage_settings as ss
from chatballs.testing import TenantAPIClient
from chatballs.webchat.test_widget_assets import png
from chatballs.webchat.testing import create_web_widget


class WidgetAssetRuntimeRoleTests(TransactionTestCase):
    def setUp(self) -> None:
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        ss.invalidate_cache()
        self.addCleanup(ss.invalidate_cache)

        result = bootstrap_owner(email="rls-assets@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        channel = Channel.objects.create(organization=self.organization, code="site", name="Сайт")
        self.integration = create_web_widget(channel).integration
        self.owner = result.owner

        other = Organization.objects.create(name="Other", slug="rls-assets-other")
        self.other_owner = HumanUser.objects.create_user(email="rls-assets-other@example.com")
        OrganizationMembership.objects.create(
            organization=other, user=self.other_owner, role=EmployeeRole.OWNER, position_title="Owner"
        )
        self.other = other

    def _as_app_role(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE chatballs_runtime_app")
        try:
            return request()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def _upload(self, user, organization: Organization):
        client = TenantAPIClient()
        client.force_authenticate(user)
        return client.post(
            f"/api/v1/organizations/{organization.public_id}/integrations/{self.integration.id}/assets/",
            {"file": SimpleUploadedFile("icon.png", png(96, 96))},
            format="multipart",
        )

    def test_upload_and_public_download_work_under_app_role(self) -> None:
        uploaded = self._as_app_role(lambda: self._upload(self.owner, self.organization))
        self.assertEqual(uploaded.status_code, 201, uploaded.content)

        served = self._as_app_role(lambda: APIClient().get(uploaded.json()["url"]))

        self.assertEqual(served.status_code, 200)
        self.assertEqual(b"".join(served.streaming_content), png(96, 96))

    def test_foreign_organization_cannot_reach_the_widget_under_app_role(self) -> None:
        response = self._as_app_role(lambda: self._upload(self.other_owner, self.other))

        self.assertEqual(response.status_code, 404)
