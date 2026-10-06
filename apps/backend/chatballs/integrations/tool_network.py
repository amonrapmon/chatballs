"""Куда инструментам агента ходить можно: проверка адреса после DNS.

Адрес внешнего сервера вводит администратор организации, а итоговый адрес
запроса собирается из параметров, часть которых заполняет модель. Доверия к
нему меньше, чем к ``base_url`` LLM-провайдера (``integrations.outbound``):
здесь запрещено всё, что ведёт внутрь, и проверяется не имя, а IP, на который
оно разрешилось, — на него же потом идёт соединение (``tool_client``).

Три уровня (SPEC-0023 R-16, R-17):

* loopback, link-local, multicast и сервисы самой установки закрыты всегда;
* частные диапазоны закрыты, пока администратор установки не включил
  «адреса локальной сети для инструментов»;
* остальное открыто, если адрес публичный.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from django.conf import settings

from chatballs.i18n import t
from chatballs.integrations.outbound import HTTP_SCHEMES, OutboundUrlRejected, resolve_host

# Диапазоны, которые открывает настройка установки: RFC 1918, адреса за
# провайдерским NAT (RFC 6598) и локальные адреса IPv6 (RFC 4193).
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "fc00::/7")
)

_SERVICE_CACHE_TTL_SECONDS = 60.0
_service_cache: tuple[float, frozenset[str]] | None = None


class ToolAddressRejected(OutboundUrlRejected):
    """Адрес инструмента не разрешён; ``code`` — причина для журнала и модели."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ToolTarget:
    """Проверенный адрес: имя хоста для Host и TLS, IP — для соединения."""

    scheme: str
    host: str
    port: int
    address: str
    request_target: str


def check_tool_url(url: str, *, allow_private: bool | None = None) -> ToolTarget:
    """Проверить адрес инструмента и вернуть IP, на который можно соединяться.

    ``allow_private`` — разрешены ли частные диапазоны; без значения берётся
    настройка установки. Проверяются все адреса имени: один внутренний среди
    них — отказ, иначе выбор между ними делал бы резолвер, а не политика.
    """
    parsed = urlsplit(str(url or "").strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    if scheme not in HTTP_SCHEMES or not host:
        allowed = ", ".join(f"{item}://" for item in sorted(HTTP_SCHEMES))
        raise ToolAddressRejected("scheme", t("settings.url_scheme_required", schemes=allowed))
    try:
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError:
        raise _internal() from None
    if host in service_hosts():
        raise _internal()
    addresses = resolve_host(host, port)
    if not addresses:
        raise ToolAddressRejected("unresolved", t("integrations.tool_address_unresolved"))
    if allow_private is None:
        from chatballs.identity.instance_settings import tools_private_network_allowed

        allow_private = tools_private_network_allowed()
    services = _service_addresses()
    for address in addresses:
        if not _is_allowed(address, allow_private=allow_private, services=services):
            raise _internal()
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    return ToolTarget(scheme, host, port, addresses[0], target)


def service_hosts() -> frozenset[str]:
    """Имена сервисов установки: из настроек, базы, кэша и сам этот узел."""
    names = {str(name) for name in getattr(settings, "CHATBALLS_INSTANCE_SERVICE_HOSTS", ())}
    names.add(str(settings.DATABASES.get("default", {}).get("HOST") or ""))
    names.add(urlsplit(str(settings.CACHES.get("default", {}).get("LOCATION") or "")).hostname or "")
    names.add(socket.gethostname())
    # Путь к сокету — не имя хоста.
    return frozenset(
        name.strip().lower().rstrip(".") for name in names if name.strip() and "/" not in name
    )


def reset_service_cache() -> None:
    global _service_cache
    _service_cache = None


def _internal() -> ToolAddressRejected:
    return ToolAddressRejected("internal", t("integrations.tool_address_local"))


def _service_addresses() -> frozenset[str]:
    """IP сервисов установки: имя сервиса можно обойти, записав его адрес числом.

    Кэш на минуту: имён полтора десятка, а проверка стоит на каждом запросе
    инструмента и на каждом перенаправлении.
    """
    global _service_cache
    now = time.monotonic()
    if _service_cache is not None and now - _service_cache[0] < _SERVICE_CACHE_TTL_SECONDS:
        return _service_cache[1]
    addresses = frozenset(
        str(_normalize(address)) for name in service_hosts() for address in resolve_host(name, 80)
    )
    _service_cache = (now, addresses)
    return addresses


def _normalize(address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Адрес без IPv6-обёртки: ``::ffff:127.0.0.1`` — это всё тот же loopback."""
    ip = ipaddress.ip_address(address)
    return getattr(ip, "ipv4_mapped", None) or ip


def _is_allowed(address: str, *, allow_private: bool, services: frozenset[str]) -> bool:
    ip = _normalize(address)
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return False
    if str(ip) in services:
        return False
    if ip.is_global:
        return True
    return allow_private and any(ip in network for network in PRIVATE_NETWORKS)
