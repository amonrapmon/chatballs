"""Транспорт ВКонтакте: разбор апдейтов, курсор Long Poll, отправка.

Тесты идут без базы: транспорту нужны только поля подключения, поэтому вместо
записи в базу здесь простая заглушка. Сеть закрыта подменой вызова API и
опроса сервера событий.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from chatballs.conversations.transports import vk, vk_media, vk_send
from chatballs.conversations.transports.errors import PollFailed
from chatballs.integrations.checks import VkRejected

SERVER = {"server": "https://lp.vk.com/wh1", "key": "lp-key", "ts": "100"}
PROFILE = {"id": 77, "first_name": "Иван", "last_name": "Петров", "screen_name": "ivan", "photo_100": "https://vk.com/ivan.jpg"}


def _integration(**config):
    return SimpleNamespace(
        id=1,
        secret="vk-community-token",
        poll_marker="",
        config={"bot_id": "42", **config},
        organization=SimpleNamespace(language="ru"),
    )


def _update(**message):
    payload = {"from_id": 77, "peer_id": 77, "id": 500, "text": "Здравствуйте", **message}
    return {"type": "message_new", "object": {"message": payload}}


class _Api:
    """Подмена вызова API: ответ на метод и журнал обращений."""

    def __init__(self, **responses):
        self.responses = {"users.get": [PROFILE], "groups.getLongPollServer": SERVER, **responses}
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, integration, method, params=None, *, post=False):
        self.calls.append((method, dict(params or {})))
        response = self.responses.get(method)
        if isinstance(response, Exception):
            raise response
        return response

    def methods(self) -> list[str]:
        return [method for method, _params in self.calls]

    def params(self, method: str) -> dict:
        return next(params for name, params in self.calls if name == method)


class VkInboundTests(SimpleTestCase):
    def setUp(self) -> None:
        vk.reset()
        self.addCleanup(vk.reset)

    def _poll(self, check_result, *, api=None, integration=None):
        api = api or _Api()
        integration = integration or _integration()
        with mock.patch.object(vk.vk_api, "call", api):
            with mock.patch.object(vk, "request_json", return_value=check_result) as request:
                messages, marker = vk.poll_updates(integration)
        return messages, marker, api, request

    def test_message_becomes_inbound_with_profile_from_one_request(self) -> None:
        api = _Api()
        messages, marker, api, _request = self._poll(
            {"ts": "101", "updates": [_update(), _update(id=501, text="Ещё вопрос")]},
            api=api,
        )
        self.assertEqual(marker, "101")
        self.assertEqual([message.text for message in messages], ["Здравствуйте", "Ещё вопрос"])
        self.assertEqual(messages[0].external_id, "500")
        self.assertEqual(messages[0].user_id, "77")
        self.assertEqual(messages[0].chat_id, "77")
        self.assertEqual(messages[0].display_name, "Иван Петров")
        self.assertEqual(messages[0].username, "ivan")
        self.assertEqual(messages[0].avatar_url, "https://vk.com/ivan.jpg")
        # Профиль спрашивается один раз на пачку, а не на каждое сообщение.
        self.assertEqual(api.methods().count("users.get"), 1)
        self.assertEqual(api.params("users.get")["user_ids"], "77")

    def test_community_own_message_and_other_events_are_ignored(self) -> None:
        messages, _marker, _api, _request = self._poll(
            {
                "ts": "102",
                "updates": [
                    _update(from_id=-42),
                    {"type": "group_join", "object": {"user_id": 77}},
                ],
            }
        )
        self.assertEqual(messages, [])

    def test_profile_failure_does_not_lose_the_message(self) -> None:
        api = _Api(**{"users.get": VkRejected("VK отклонил запрос")})
        messages, _marker, _api, _request = self._poll({"ts": "103", "updates": [_update()]}, api=api)
        self.assertEqual([message.text for message in messages], ["Здравствуйте"])
        self.assertEqual(messages[0].display_name, "")

    def test_first_cycle_takes_position_from_vk_and_next_one_from_the_marker(self) -> None:
        api = _Api()
        integration = _integration()
        with mock.patch.object(vk.vk_api, "call", api):
            with mock.patch.object(vk, "request_json", return_value={"ts": "101", "updates": []}) as request:
                vk.poll_updates(integration)
                integration.poll_marker = "101"
                vk.poll_updates(integration)
        self.assertIn("ts=100", request.call_args_list[0].args[0])
        self.assertIn("ts=101", request.call_args_list[1].args[0])
        # Адрес Long Poll выдаётся один раз и живёт в памяти процесса.
        self.assertEqual(api.methods().count("groups.getLongPollServer"), 1)

    def test_zero_position_of_a_fresh_community_is_kept(self) -> None:
        # Сообществу, которому ещё не писали, ВКонтакте отдаёт ts=0. Пустая
        # позиция в опросе возвращает ts=-1 — курсор, с которого поток уже не
        # читается, и первое же сообщение клиента прошло бы мимо.
        api = _Api()
        api.responses["groups.getLongPollServer"] = {**SERVER, "ts": 0}
        with mock.patch.object(vk.vk_api, "call", api):
            with mock.patch.object(vk, "request_json", return_value={"ts": "0", "updates": []}) as request:
                _messages, marker = vk.poll_updates(_integration())
        self.assertIn("ts=0", request.call_args_list[0].args[0])
        self.assertEqual(marker, "0")

    def test_outdated_position_is_retried_with_the_one_vk_returned(self) -> None:
        api = _Api()
        integration = _integration()
        integration.poll_marker = "90"
        answers = [{"failed": 1, "ts": "100"}, {"ts": "101", "updates": [_update()]}]
        with mock.patch.object(vk.vk_api, "call", api):
            with mock.patch.object(vk, "request_json", side_effect=answers) as request:
                messages, marker = vk.poll_updates(integration)
        self.assertEqual(marker, "101")
        self.assertEqual(len(messages), 1)
        self.assertIn("ts=100", request.call_args_list[1].args[0])

    def test_expired_key_takes_a_new_one_and_keeps_the_position(self) -> None:
        api = _Api()
        api.responses["groups.getLongPollServer"] = {**SERVER, "key": "fresh-key", "ts": "900"}
        integration = _integration()
        integration.poll_marker = "90"
        answers = [{"failed": 2}, {"ts": "91", "updates": []}]
        with mock.patch.object(vk.vk_api, "call", api):
            with mock.patch.object(vk, "request_json", side_effect=answers) as request:
                _messages, marker = vk.poll_updates(integration)
        self.assertEqual(marker, "91")
        retry_url = request.call_args_list[1].args[0]
        self.assertIn("key=fresh-key", retry_url)
        self.assertIn("ts=90", retry_url)

    def test_lost_history_takes_both_the_key_and_the_position(self) -> None:
        api = _Api()
        api.responses["groups.getLongPollServer"] = {**SERVER, "key": "fresh-key", "ts": "900"}
        integration = _integration()
        integration.poll_marker = "90"
        answers = [{"failed": 3}, {"ts": "901", "updates": []}]
        with mock.patch.object(vk.vk_api, "call", api):
            with mock.patch.object(vk, "request_json", side_effect=answers) as request:
                _messages, marker = vk.poll_updates(integration)
        self.assertEqual(marker, "901")
        self.assertIn("ts=900", request.call_args_list[1].args[0])

    def test_broken_connection_is_a_poll_failure_and_forgets_the_session(self) -> None:
        api = _Api()
        integration = _integration()
        with mock.patch.object(vk.vk_api, "call", api):
            with mock.patch.object(vk, "request_json", side_effect=TimeoutError("timed out")):
                with self.assertRaises(PollFailed):
                    vk.poll_updates(integration)
        self.assertEqual(vk._sessions, {})

    def test_token_never_leaks_into_the_failure_text(self) -> None:
        api = _Api()
        leak = OSError("HTTP Error 401: https://api.vk.com/method/users.get?access_token=vk1.a.SECRET&v=5.199")
        with mock.patch.object(vk.vk_api, "call", api):
            with mock.patch.object(vk, "request_json", side_effect=leak):
                with self.assertRaises(PollFailed) as failure:
                    vk.poll_updates(_integration())
        self.assertNotIn("vk1.a.SECRET", str(failure.exception))
        self.assertIn("access_token=***", str(failure.exception))

    def test_group_is_asked_once_when_the_connection_was_never_checked(self) -> None:
        api = _Api(**{"groups.getById": {"groups": [{"id": 42, "name": "Acme"}]}})
        integration = _integration()
        integration.config.pop("bot_id")
        with mock.patch.object(vk.vk_api, "call", api):
            with mock.patch.object(vk, "request_json", return_value={"ts": "101", "updates": []}):
                vk.poll_updates(integration)
        self.assertEqual(api.params("groups.getLongPollServer")["group_id"], "42")


class VkAttachmentTests(SimpleTestCase):
    def setUp(self) -> None:
        vk.reset()
        self.addCleanup(vk.reset)

    def test_photo_takes_the_largest_size(self) -> None:
        attachment = {
            "type": "photo",
            "photo": {"sizes": [
                {"url": "https://vk.com/small.jpg", "width": 75, "height": 75},
                {"url": "https://vk.com/large.jpg", "width": 1280, "height": 960},
            ]},
        }
        files = vk_media.file_attachments({"attachments": [attachment]})
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].url, "https://vk.com/large.jpg")
        self.assertTrue(files[0].is_image)

    def test_document_keeps_its_name_and_size(self) -> None:
        attachment = {"type": "doc", "doc": {"url": "https://vk.com/f.pdf", "title": "Счёт.pdf", "size": 2048}}
        files = vk_media.file_attachments({"attachments": [attachment]})
        self.assertEqual(files[0].name, "Счёт.pdf")
        self.assertEqual(files[0].content_type, "application/pdf")
        self.assertEqual(files[0].size, 2048)
        self.assertFalse(files[0].is_image)

    def test_voice_message_is_taken_in_ogg(self) -> None:
        attachment = {
            "type": "audio_message",
            "audio_message": {"duration": 7, "link_ogg": "https://vk.com/v.ogg", "link_mp3": "https://vk.com/v.mp3"},
        }
        url, duration, mime, unavailable = vk_media.voice_attachment({"attachments": [attachment]})
        self.assertEqual((url, duration, mime, unavailable), ("https://vk.com/v.ogg", 7, "audio/ogg", False))

    def test_voice_without_a_link_still_reaches_the_operator(self) -> None:
        _url, _duration, _mime, unavailable = vk_media.voice_attachment(
            {"attachments": [{"type": "audio_message", "audio_message": {"duration": 3}}]}
        )
        self.assertTrue(unavailable)

    def test_attachment_the_channel_cannot_show_does_not_swallow_the_message(self) -> None:
        update = _update(text="", attachments=[{"type": "video", "video": {"id": 1}}])
        with mock.patch.object(vk, "customer_language", return_value="ru"):
            message = vk._normalize(_integration(), update)
        self.assertIsNotNone(message)
        self.assertTrue(message.text)


class VkOutboundTests(SimpleTestCase):
    def test_text_goes_out_by_post_with_a_deduplication_id(self) -> None:
        api = _Api(**{"messages.send": {"response": 1}})
        posts = []

        def record(integration, method, params=None, *, post=False):
            posts.append(post)
            return api(integration, method, params, post=post)

        with mock.patch.object(vk_send.vk_api, "call", record):
            self.assertTrue(vk_send.send_text(_integration(), chat_id="77", user_id="77", text="Ответ"))
        params = api.params("messages.send")
        self.assertEqual(params["peer_id"], "77")
        self.assertEqual(params["message"], "Ответ")
        self.assertTrue(params["random_id"])
        self.assertEqual(posts, [True])

    def test_call_invite_carries_a_link_button(self) -> None:
        api = _Api(**{"messages.send": {"response": 1}})
        with mock.patch.object(vk_send.vk_api, "call", api):
            with mock.patch.object(vk_send, "customer_language", return_value="ru"):
                sent = vk_send.send_call_invite(
                    _integration(), chat_id="77", user_id="77", text="Звонок", url="https://chatballs.test/calls/abc"
                )
        self.assertTrue(sent)
        self.assertIn("https://chatballs.test/calls/abc", api.params("messages.send")["keyboard"])

    def test_rejected_send_is_reported_as_failure(self) -> None:
        api = _Api(**{"messages.send": VkRejected("ВКонтакте отклонил запрос (7): access denied")})
        with mock.patch.object(vk_send.vk_api, "call", api):
            self.assertFalse(vk_send.send_text(_integration(), chat_id="77", user_id="", text="Ответ"))

    def test_photo_is_uploaded_and_attached(self) -> None:
        api = _Api(
            **{
                "photos.getMessagesUploadServer": {"upload_url": "https://upload.vk.com/1"},
                "photos.saveMessagesPhoto": [{"owner_id": 5, "id": 9}],
                "messages.send": {"response": 1},
            }
        )
        with mock.patch.object(vk_send.vk_api, "call", api):
            with mock.patch.object(
                vk_media, "request_json_multipart", return_value={"server": "1", "photo": "[]", "hash": "h"}
            ):
                sent = vk_send.send_file(
                    _integration(),
                    chat_id="77",
                    user_id="77",
                    content=b"binary",
                    filename="photo.jpg",
                    content_type="image/jpeg",
                    caption="Схема",
                )
        self.assertTrue(sent)
        self.assertEqual(api.params("messages.send")["attachment"], "photo5_9")
        self.assertEqual(api.params("messages.send")["message"], "Схема")
