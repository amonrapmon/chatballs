"""Доступ к API ВКонтакте: адрес подключения, прокси, вызов метода, скачивание.

Ключ доступа сообщества уходит параметром запроса — заголовка авторизации у
ВКонтакте нет. Поэтому ни один адрес не печатается как есть: и журнал, и статус
подключения получают его через ``mask_url_secrets``.
"""

from __future__ import annotations

import http.client
import json
import urllib.error

from chatballs.conversations.transports.base import download_bytes
from chatballs.integrations.checks import DEFAULT_VK_BASE_URL, VkRejected, vk_call
from chatballs.integrations.outbound import host_of

NETWORK_ERRORS = (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, json.JSONDecodeError)
# Отказ провайдера и обрыв связи обрабатываются одинаково: подключение на этом
# цикле не работает, а чем именно — видно из текста ошибки.
CALL_ERRORS = (VkRejected, *NETWORK_ERRORS)


def base(integration) -> str:
    return (integration.config.get("base_url") or DEFAULT_VK_BASE_URL).rstrip("/")


def proxy(integration) -> str:
    return integration.config.get("proxy_url", "")


def call(integration, method: str, params: dict | None = None, *, post: bool = False):
    """Метод API ВКонтакте от имени подключения; возвращает содержимое response."""
    return vk_call(
        base_url=base(integration),
        method=method,
        secret=integration.secret,
        params=params,
        proxy_url=proxy(integration),
        post=post,
    )


def download(integration, url: str) -> bytes:
    """Скачивание по прямому адресу из ответа провайдера.

    Хост из ``base_url`` подключения владелец назвал сам, поэтому он остаётся
    разрешённым, даже если ведёт внутрь сети (chatballs.integrations.outbound).
    """
    return download_bytes(url, proxy_url=proxy(integration), allowed_host=host_of(base(integration)))
