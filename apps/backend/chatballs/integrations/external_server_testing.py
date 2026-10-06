"""Основа тестов интеграции «Внешний сервер»: подменённый DNS и пример запроса."""

from __future__ import annotations

from django.test import TestCase, override_settings

from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.instance_settings import InstanceSettings
from chatballs.identity.models import Organization
from chatballs.integrations.tool_testing import PUBLIC_IP, fake_dns
from chatballs.testing import TenantAPIClient

DNS = {
    "shop.example.test": [PUBLIC_IP],
    "mcp.example.test": [PUBLIC_IP],
    "postgres": ["172.20.0.5"],
}
URL = "/api/v1/integrations/"
TOKEN = "Bearer shop-secret-token"


def order_status(**overrides: object) -> dict:
    return {
        "description": "Статус заказа по номеру",
        "toolName": "get_order_status",
        "method": "GET",
        "url": "https://shop.example.test/api/orders/{order_number}",
        "parameters": [
            {"name": "order_number", "type": "string", "location": "path", "source": {"type": "ai"}},
            {
                "name": "include_items",
                "type": "boolean",
                "description": "Нужен ли состав заказа",
                "required": False,
                "location": "query",
            },
        ],
        "headers": [
            {"name": "Authorization", "secret": True, "value": TOKEN},
            {"name": "X-Shop-Id", "secret": False, "value": "obed-main"},
        ],
        **overrides,
    }


@override_settings(CHATBALLS_INSTANCE_SERVICE_HOSTS=["postgres", "redis"])
class ExternalServerTestCase(TestCase):
    def setUp(self) -> None:
        fake_dns(self, DNS)
        bootstrap_owner(email="external-owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.client = TenantAPIClient()
        self.client.login(username="external-owner@example.com", password="temporary-password")

    def _create(self, provider: str, settings: object, name: str = "Статус заказа"):
        return self.client.post(
            URL, {"provider": provider, "name": name, "externalServer": settings}, format="json"
        )

    def _errors(self, response) -> dict:
        self.assertEqual(response.status_code, 400, response.content)
        return response.json()["errors"]

    def _allow_private_network(self) -> None:
        row = InstanceSettings.load()
        row.tools_private_network = True
        row.save(update_fields=["tools_private_network", "updated_at"])
