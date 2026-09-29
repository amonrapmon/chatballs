"""Иконки виджета: загрузка, очистка, хранилище организации и публичная отдача.

SPEC-0021 R-3, R-4: SVG или PNG до 256 КБ (PNG не меньше 96×96) →
``{ url }``; файл лежит под ``organizations/{public_id}/`` на диске или в S3 и
открывается на чужом сайте без сессии.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from chatballs.channels.models import Channel
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import EmployeeRole, HumanUser, Organization, OrganizationMembership
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.tenancy import storage_settings as ss
from chatballs.tenancy.storage_backends import DynamicTenantStorage
from chatballs.testing import TenantAPIClient
from chatballs.webchat.models import WidgetAsset
from chatballs.webchat.test_svg_sanitizer import HARMFUL_SVG
from chatballs.webchat.testing import create_web_widget


def png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    pixels = zlib.compress(b"".join(b"\x00" + b"\x80" * width for _ in range(height)))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


class WidgetAssetApiTests(TestCase):
    def setUp(self) -> None:
        self.media = TemporaryDirectory()
        self.bucket = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.addCleanup(self.bucket.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        ss.invalidate_cache()
        self.addCleanup(ss.invalidate_cache)
        DynamicTenantStorage._s3_cache = None

        result = bootstrap_owner(email="assets-owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        channel = Channel.objects.create(organization=self.organization, code="site", name="Сайт")
        self.integration = create_web_widget(channel).integration
        self.client = TenantAPIClient()
        self.client.force_authenticate(result.owner)

    def _url(self, integration_id: int, organization: Organization | None = None) -> str:
        public_id = (organization or self.organization).public_id
        return f"/api/v1/organizations/{public_id}/integrations/{integration_id}/assets/"

    def _upload(self, name: str, data: bytes, *, client=None, url: str | None = None):
        return (client or self.client).post(
            url or self._url(self.integration.id),
            {"file": SimpleUploadedFile(name, data, content_type="application/octet-stream")},
            format="multipart",
        )

    def _anonymous_get(self, url: str):
        return APIClient().get(url, HTTP_ORIGIN="https://customer-site.example")

    def _enable_s3(self) -> None:
        patcher = mock.patch.object(
            ss, "build_s3_storage", lambda config, **kwargs: FileSystemStorage(location=self.bucket.name)
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        row = ss.StorageSettings.load()
        row.backend = ss.StorageBackend.S3
        row.s3_bucket = "demo"
        row.s3_access_key = "AKIA-demo-access"
        row.s3_secret_key = "very-secret"
        row.save()
        DynamicTenantStorage._s3_cache = None

    def _second_owner_client(self) -> tuple[Organization, TenantAPIClient]:
        other = Organization.objects.create(name="Other", slug="other")
        owner = HumanUser.objects.create_user(email="other-owner@example.com", password="Password-123", full_name="Other")
        OrganizationMembership.objects.create(organization=other, user=owner, role=EmployeeRole.OWNER, position_title="Owner")
        client = TenantAPIClient()
        client.force_authenticate(owner)
        return other, client

    # --- приём и отказ -------------------------------------------------------

    def test_harmful_svg_is_cleaned_and_served_without_session(self) -> None:
        response = self._upload("logo.svg", HARMFUL_SVG)

        self.assertEqual(response.status_code, 201, response.content)
        url = response.json()["url"]
        self.assertRegex(url, r"^/api/v1/webchat/assets/[0-9a-f-]{36}/$")
        served = self._anonymous_get(url)
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served["Content-Type"], "image/svg+xml")
        self.assertEqual(served["Cross-Origin-Resource-Policy"], "cross-origin")
        self.assertEqual(served["X-Content-Type-Options"], "nosniff")
        self.assertIn("sandbox", served["Content-Security-Policy"])
        body = b"".join(served.streaming_content).lower()
        for forbidden in (b"<script", b"foreignobject", b"onload", b"onclick", b"javascript:", b"evil.example"):
            self.assertNotIn(forbidden, body)
        self.assertIn(b'<circle class="mark"', body)

    def test_png_from_96_pixels_is_stored_as_is(self) -> None:
        data = png(96, 128)

        response = self._upload("icon.png", data)

        self.assertEqual(response.status_code, 201, response.content)
        served = self._anonymous_get(response.json()["url"])
        self.assertEqual(served["Content-Type"], "image/png")
        self.assertEqual(b"".join(served.streaming_content), data)

    def test_unsuitable_files_are_refused_with_a_clear_message(self) -> None:
        cases = {
            "small png": ("icon.png", png(95, 200), "PNG должен быть не меньше 96×96 пикселей"),
            "too large": ("icon.png", png(96, 96) + b"\x00" * (256 * 1024), "Размер иконки не должен превышать 256 КБ"),
            "gif": ("icon.gif", b"GIF89a\x01\x00\x01\x00", "Поддерживаются SVG и PNG"),
            "svg named png": ("icon.png", b"<html><script>alert(1)</script></html>", "Поддерживаются SVG и PNG"),
            "broken svg": ("icon.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><rect></svg>', "Не удалось прочитать SVG. Сохраните файл заново в графическом редакторе"),
            "empty": ("icon.svg", b"", "Выберите файл иконки"),
        }
        for name, (filename, data, message) in cases.items():
            with self.subTest(name):
                response = self._upload(filename, data)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(response.json()["detail"], message)
                self.assertEqual(response.json()["errors"], {"file": message})
        self.assertFalse(WidgetAsset.objects.exists())

    def test_only_web_widget_accepts_icons(self) -> None:
        provider = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.LLM_PROVIDER,
            provider=IntegrationProvider.DEMO,
            name="Demo",
        )

        response = self._upload("icon.png", png(96, 96), url=self._url(provider.id))

        self.assertEqual(response.status_code, 404)

    # --- хранилище ----------------------------------------------------------

    def test_file_lives_in_organization_folder_on_disk(self) -> None:
        response = self._upload("icon.png", png(96, 96))

        self.assertEqual(response.status_code, 201, response.content)
        asset = WidgetAsset.objects.get()
        prefix = f"organizations/{self.organization.public_id}/webchat/{self.integration.id}/"
        self.assertTrue(asset.file.name.startswith(prefix), asset.file.name)
        self.assertTrue((Path(self.media.name) / asset.file.name).is_file())

    def test_file_lives_in_organization_folder_on_s3(self) -> None:
        self._enable_s3()

        response = self._upload("logo.svg", HARMFUL_SVG)

        self.assertEqual(response.status_code, 201, response.content)
        asset = WidgetAsset.objects.get()
        self.assertTrue(asset.file.name.startswith(f"organizations/{self.organization.public_id}/webchat/"))
        self.assertTrue((Path(self.bucket.name) / asset.file.name).is_file())
        self.assertFalse((Path(self.media.name) / asset.file.name).exists())
        served = self._anonymous_get(response.json()["url"])
        self.assertEqual(served.status_code, 200)
        self.assertNotIn(b"<script", b"".join(served.streaming_content))

    def test_deleting_widget_integration_removes_icon_files(self) -> None:
        self._upload("icon.png", png(96, 96))
        path = Path(self.media.name) / WidgetAsset.objects.get().file.name

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(
                f"/api/v1/organizations/{self.organization.public_id}/integrations/{self.integration.id}/"
            )

        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(WidgetAsset.objects.exists())
        self.assertFalse(path.exists())

    # --- изоляция -----------------------------------------------------------

    def test_other_organization_cannot_upload_to_foreign_widget(self) -> None:
        other, client = self._second_owner_client()

        through_own = self._upload("icon.png", png(96, 96), client=client, url=self._url(self.integration.id, other))
        through_foreign = self._upload("icon.png", png(96, 96), client=client)

        self.assertEqual(through_own.status_code, 404)
        self.assertIn(through_foreign.status_code, (403, 404))
        self.assertFalse(WidgetAsset.objects.exists())

    def test_every_upload_gets_its_own_address(self) -> None:
        first = self._upload("icon.png", png(96, 96)).json()["url"]
        second = self._upload("icon.png", png(128, 128)).json()["url"]

        self.assertNotEqual(first, second)
        served = self._anonymous_get(first)
        self.assertEqual(b"".join(served.streaming_content), png(96, 96))

    def test_unknown_address_is_not_found(self) -> None:
        response = self._anonymous_get("/api/v1/webchat/assets/00000000-0000-4000-8000-000000000000/")

        self.assertEqual(response.status_code, 404)
