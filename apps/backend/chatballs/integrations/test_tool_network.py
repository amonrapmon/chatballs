"""Адреса инструментов агента: что закрыто всегда, а что открывает настройка."""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from chatballs.integrations.outbound import OutboundUrlRejected
from chatballs.integrations.tool_network import ToolAddressRejected, check_tool_url
from chatballs.integrations.tool_testing import PUBLIC_IP, fake_dns

DNS = {
    "shop.example.test": [PUBLIC_IP],
    "intranet.example.test": ["192.168.1.20"],
    "rebind.example.test": [PUBLIC_IP, "127.0.0.1"],
    "loop.example.test": ["127.0.0.1"],
    "postgres": ["172.20.0.5"],
}


@override_settings(CHATBALLS_INSTANCE_SERVICE_HOSTS=["postgres", "redis"])
class ToolAddressPolicyTests(SimpleTestCase):
    def setUp(self) -> None:
        fake_dns(self, DNS)

    def assert_rejected(self, url: str, *, allow_private: bool, code: str = "internal") -> None:
        with self.subTest(url=url), self.assertRaises(ToolAddressRejected) as raised:
            check_tool_url(url, allow_private=allow_private)
        self.assertEqual(raised.exception.code, code)

    def test_public_name_resolves_to_the_checked_address(self) -> None:
        target = check_tool_url("https://shop.example.test/api/orders/7?full=1", allow_private=False)

        self.assertEqual(
            (target.scheme, target.host, target.port, target.address, target.request_target),
            ("https", "shop.example.test", 443, PUBLIC_IP, "/api/orders/7?full=1"),
        )

    def test_internal_addresses_are_refused(self) -> None:
        for url in (
            "http://127.0.0.1:8000/",
            "http://[::1]/",
            "http://[::ffff:127.0.0.1]/",
            "http://0.0.0.0/",
            "http://169.254.169.254/latest/meta-data/",
            "http://[fe80::1]/",
            "http://224.0.0.1/",
            "http://10.0.0.5/",
            "http://192.168.1.20/",
            "http://172.16.4.4/",
            "http://[fd00::1]/",
            "http://loop.example.test/",
            "http://intranet.example.test/",
        ):
            self.assert_rejected(url, allow_private=False)

    def test_installation_services_are_refused_by_name_and_by_address(self) -> None:
        for url in ("http://postgres:5432/", "http://POSTGRES/", "http://redis:6379/", "http://172.20.0.5/"):
            self.assert_rejected(url, allow_private=False)

    def test_one_internal_address_among_several_refuses_the_name(self) -> None:
        self.assert_rejected("http://rebind.example.test/", allow_private=False)

    def test_unresolved_name_is_refused(self) -> None:
        self.assert_rejected("https://nowhere.example.test/", allow_private=False, code="unresolved")

    def test_only_http_schemes_are_accepted(self) -> None:
        for url in ("file:///etc/passwd", "ftp://shop.example.test/x", "gopher://shop.example.test/", "http:///x"):
            self.assert_rejected(url, allow_private=False, code="scheme")

    def test_rejection_is_an_outbound_policy_error(self) -> None:
        with self.assertRaises(OutboundUrlRejected):
            check_tool_url("http://10.0.0.5/", allow_private=False)

    def test_setting_opens_private_ranges(self) -> None:
        for url, address in (
            ("http://192.168.1.20/", "192.168.1.20"),
            ("http://10.0.0.5:8080/x", "10.0.0.5"),
            ("http://intranet.example.test/", "192.168.1.20"),
            ("http://[fd00::1]/", "fd00::1"),
        ):
            with self.subTest(url=url):
                self.assertEqual(check_tool_url(url, allow_private=True).address, address)

    def test_setting_does_not_open_loopback_or_services(self) -> None:
        for url in (
            "http://127.0.0.1/",
            "http://[::1]/",
            "http://loop.example.test/",
            "http://169.254.169.254/",
            "http://224.0.0.1/",
            "http://postgres:5432/",
            "http://172.20.0.5/",
            "http://rebind.example.test/",
        ):
            self.assert_rejected(url, allow_private=True)
