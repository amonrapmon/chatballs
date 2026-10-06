"""HTTP-редактор проверяет адрес до сохранения, без вызова инструмента."""
from unittest.mock import patch

from chatballs.i18n import t
from chatballs.integrations.external_server_testing import URL, ExternalServerTestCase
from chatballs.integrations.models import Integration


class HttpAddressValidationTests(ExternalServerTestCase):
    def validate(self, url: str):
        return self.client.post(f"{URL}http/validate-address/", {"url": url}, format="json")

    def test_validates_without_saving_or_sending_http(self):
        count = Integration.objects.count()
        with patch("http.client.HTTPConnection.request") as send:
            response = self.validate("https://shop.example.test/orders/{order_number}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"errors": {}})
        self.assertEqual(Integration.objects.count(), count)
        send.assert_not_called()

    def test_rejects_private_addresses_and_service_hosts(self):
        for host in ("192.168.1.20", "postgres", "127.0.0.1"):
            with self.subTest(host=host):
                response = self.validate(f"http://{host}/orders/{{order_number}}")
                self.assertEqual(response.json(), {"errors": {"url": [t("integrations.tool_address_local")]}})

    def test_obeys_installation_setting_without_allowing_services(self):
        self._allow_private_network()
        self.assertEqual(self.validate("http://192.168.1.20/orders").json(), {"errors": {}})
        self.assertIn("url", self.validate("http://postgres/orders").json()["errors"])

    def test_requires_authenticated_management_access(self):
        self.client.logout()
        self.assertIn(self.validate("https://shop.example.test/orders").status_code, (401, 403, 404))
