"""Базовый домен порталов берётся из адреса установки.

Переменную окружения в коробке задавать негде (у продукта нет .env), а её
прежнее умолчание — localhost — оставляло портал на help.localhost даже там,
где установка работает на живом домене: в диалоге создания владелец видел
суффикс, которого у него нет.
"""

from __future__ import annotations

from importlib import import_module

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from chatballs.identity.instance_settings import InstanceSettings, invalidate_cache
from chatballs.support_portals.addressing import help_base_domain, hosted_domain
from chatballs.support_portals.models import SupportPortal
from chatballs.support_portals.tests.base import SupportPortalTestCase


class HelpBaseDomainTests(TestCase):
    def setUp(self) -> None:
        invalidate_cache()
        self.addCleanup(invalidate_cache)

    def _set_host(self, host: str) -> None:
        row = InstanceSettings.load()
        row.public_host = host
        row.save(update_fields=["public_host", "updated_at"])
        invalidate_cache()

    @override_settings(CHATBALLS_HELP_BASE_DOMAIN="")
    def test_installation_domain_becomes_base_domain(self) -> None:
        self._set_host("crm.example.test")

        self.assertEqual(help_base_domain(), "crm.example.test")
        self.assertEqual(hosted_domain("help"), "help.crm.example.test")

    @override_settings(CHATBALLS_HELP_BASE_DOMAIN="help.example.test")
    def test_environment_variable_overrides_installation_address(self) -> None:
        self._set_host("crm.example.test")

        self.assertEqual(help_base_domain(), "help.example.test")

    @override_settings(CHATBALLS_HELP_BASE_DOMAIN="")
    def test_installation_known_only_by_ip_has_no_base_domain(self) -> None:
        self._set_host("203.0.113.10")

        self.assertEqual(help_base_domain(), "")
        with self.assertRaises(ValidationError):
            hosted_domain("help")


class PortalCreationWithoutDomainTests(SupportPortalTestCase):
    """Пока установка известна только по IP, размещать портал негде."""

    def setUp(self) -> None:
        super().setUp()
        invalidate_cache()
        self.addCleanup(invalidate_cache)
        row = InstanceSettings.load()
        row.public_host = "203.0.113.10"
        row.save(update_fields=["public_host", "updated_at"])
        invalidate_cache()

    @override_settings(CHATBALLS_HELP_BASE_DOMAIN="")
    def test_list_reports_empty_base_domain(self) -> None:
        response = self.client.get("/api/v1/support/portals/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["address"]["baseDomain"], "")

    @override_settings(CHATBALLS_HELP_BASE_DOMAIN="")
    def test_creation_is_rejected(self) -> None:
        response = self.create_portal()

        self.assertEqual(response.status_code, 400)


class HostedDomainMigrationTests(SupportPortalTestCase):
    """Порталы, созданные до появления домена, переезжают на него миграцией."""

    def setUp(self) -> None:
        super().setUp()
        invalidate_cache()
        self.addCleanup(invalidate_cache)
        self.migration = import_module(
            "chatballs.support_portals.migrations"
            ".0011_hosted_domains_follow_installation"
        )

    def _set_host(self, host: str) -> None:
        row = InstanceSettings.load()
        row.public_host = host
        row.save(update_fields=["public_host", "updated_at"])
        invalidate_cache()

    def test_localhost_address_moves_to_the_installation_domain(self) -> None:
        self.assertEqual(self.create_portal().status_code, 201)
        portal = SupportPortal.objects.get(slug="app-help")
        self.assertEqual(portal.hosted_domain, "app-help.localhost")
        self._set_host("crm.example.test")

        with override_settings(CHATBALLS_HELP_BASE_DOMAIN=""):
            self.migration.move_hosted_domains_to_installation(django_apps, None)

        portal.refresh_from_db()
        self.assertEqual(portal.hosted_domain, "app-help.crm.example.test")

    def test_installation_without_domain_leaves_addresses_alone(self) -> None:
        self.assertEqual(self.create_portal().status_code, 201)
        self._set_host("203.0.113.10")

        with override_settings(CHATBALLS_HELP_BASE_DOMAIN=""):
            self.migration.move_hosted_domains_to_installation(django_apps, None)

        portal = SupportPortal.objects.get(slug="app-help")
        self.assertEqual(portal.hosted_domain, "app-help.localhost")
