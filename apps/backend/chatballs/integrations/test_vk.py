"""Проверка подключения ВКонтакте: кто мы и включён ли приём сообщений.

Сеть закрыта подменой HTTP-вызова: проверка обязана разбирать ответ, а не
ходить наружу. База здесь не нужна — проверка работает с секретом и адресом.
"""

from __future__ import annotations

import urllib.error
from unittest import mock

from django.test import SimpleTestCase

from chatballs.integrations import checks

GROUP = {"groups": [{"id": 42, "name": "Acme Support", "screen_name": "acme"}]}
LONG_POLL_ON = {"is_enabled": True, "events": {"message_new": 1}, "api_version": "5.199"}


def _answers(*responses):
    """Ответы VK по порядку вызовов: (status, payload)."""
    return mock.patch.object(checks, "_get", side_effect=[(200, response) for response in responses])


class VkCheckTests(SimpleTestCase):
    def test_community_is_recognized_and_remembered(self) -> None:
        with _answers({"response": GROUP}, {"response": LONG_POLL_ON}) as get:
            ok, detail, meta = checks.check_vk(secret="community-token", base_url="")
        self.assertTrue(ok)
        self.assertIn("Acme Support", detail)
        self.assertEqual(meta, {"bot_id": "42", "bot_username": "acme", "bot_name": "Acme Support"})
        # Идентификатор сообщества владелец не вводит: его называет сам токен.
        self.assertIn("groups.getById", get.call_args_list[0].args[0])
        self.assertIn("group_id=42", get.call_args_list[1].args[0])

    def test_older_api_shape_is_accepted(self) -> None:
        with _answers({"response": [{"id": 42, "name": "Acme Support"}]}, {"response": LONG_POLL_ON}):
            ok, _detail, meta = checks.check_vk(secret="community-token", base_url="")
        self.assertTrue(ok)
        self.assertEqual(meta["bot_id"], "42")

    def test_missing_token_is_reported_before_any_request(self) -> None:
        with mock.patch.object(checks, "_get") as get:
            ok, detail, _meta = checks.check_vk(secret="", base_url="")
        self.assertFalse(ok)
        self.assertTrue(detail)
        get.assert_not_called()

    def test_rejected_token_is_an_error_even_with_http_200(self) -> None:
        # ВКонтакте отвечает на отозванный ключ кодом 200 и телом error.
        rejection = {"error": {"error_code": 5, "error_msg": "User authorization failed"}}
        with _answers(rejection):
            ok, detail, meta = checks.check_vk(secret="revoked", base_url="")
        self.assertFalse(ok)
        self.assertIn("User authorization failed", detail)
        self.assertEqual(meta, {})

    def test_key_without_the_long_poll_permissions_says_what_to_fix(self) -> None:
        # ВКонтакте отвечает на нехватку прав кодом 15 и английским «no access»:
        # владельцу из него не видно, какое право включить.
        denied = {"error": {"error_code": 15, "error_msg": "Access denied: no access to call this method."}}
        with _answers({"response": GROUP}, denied):
            ok, detail, _meta = checks.check_vk(secret="messages-only", base_url="")
        self.assertFalse(ok)
        self.assertIn("Управление сообществом", detail)

    def test_personal_token_without_a_community_is_rejected(self) -> None:
        with _answers({"response": {"groups": []}}):
            ok, detail, _meta = checks.check_vk(secret="user-token", base_url="")
        self.assertFalse(ok)
        self.assertTrue(detail)

    def test_disabled_long_poll_is_an_error(self) -> None:
        with _answers({"response": GROUP}, {"response": {"is_enabled": False, "events": {}}}):
            ok, detail, meta = checks.check_vk(secret="community-token", base_url="")
        self.assertFalse(ok)
        self.assertIn("Long Poll", detail)
        # Сообщество уже опознано — идентификатор пригодится следующей проверке.
        self.assertEqual(meta["bot_id"], "42")

    def test_long_poll_without_the_message_event_is_an_error(self) -> None:
        with _answers({"response": GROUP}, {"response": {"is_enabled": True, "events": {"message_new": 0}}}):
            ok, detail, _meta = checks.check_vk(secret="community-token", base_url="")
        self.assertFalse(ok)
        self.assertTrue(detail)

    def test_broken_connection_does_not_raise(self) -> None:
        with mock.patch.object(checks, "_get", side_effect=urllib.error.URLError("no route")):
            ok, detail, _meta = checks.check_vk(secret="community-token", base_url="")
        self.assertFalse(ok)
        self.assertIn("no route", detail)

    def test_token_never_leaks_into_the_status(self) -> None:
        failure = urllib.error.HTTPError(
            "https://api.vk.com/method/groups.getById?access_token=vk1.a.SECRET&v=5.199",
            403,
            "Forbidden",
            {},
            None,
        )
        with mock.patch.object(checks, "_get", side_effect=failure):
            _ok, detail, _meta = checks.check_vk(secret="vk1.a.SECRET", base_url="")
        self.assertNotIn("vk1.a.SECRET", detail)
