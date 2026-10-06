"""Подмена DNS для тестов политики и клиента инструментов."""

from __future__ import annotations

import ipaddress
from unittest import mock

from chatballs.integrations import tool_network

PUBLIC_IP = "93.184.216.34"


def fake_dns(test_case, names: dict[str, list[str]]) -> None:
    """Имена разрешаются по словарю, числовые адреса — сами в себя."""

    def resolve(host: str, port: int) -> list[str]:
        try:
            return [str(ipaddress.ip_address(host))]
        except ValueError:
            return list(names.get(host, []))

    patcher = mock.patch.object(tool_network, "resolve_host", resolve)
    patcher.start()
    test_case.addCleanup(patcher.stop)
    tool_network.reset_service_cache()
    test_case.addCleanup(tool_network.reset_service_cache)
