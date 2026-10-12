"""Test-only HTTP helpers for the private TG/MAX network smoke."""

import json
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SECRET = "synthetic-network-only"
WEBHOOK_SECRET = "synthetic-webhook-test-only"
GATEWAYS = {"TG": "http://native-smoke-tg:3000", "MAX": "http://native-smoke-max:3000"}


def http_json(url, payload=None, headers=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url, data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST" if data is not None else "GET",
    )
    try:
        with urlopen(request, timeout=8) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


class GatewaySmokeMixin:
    def configure(self, transport, integration, *, secret=SECRET, fail_next=False):
        status, body = http_json(GATEWAYS[transport] + "/__smoke/configure", {
            "base_url": self.chatballs_url,
            "integration_id": integration.id,
            "integration_secret": secret,
            "fail_next": fail_next,
        })
        self.assertEqual((status, body), (200, {"accepted": True}))

    def state(self, transport):
        status, body = http_json(GATEWAYS[transport] + "/__smoke/state")
        self.assertEqual(status, 200)
        return body

    def callback(self, transport, *, native=False, ident="1", auth=WEBHOOK_SECRET):
        event_type = "outgoingMessageReceived" if native else "incomingMessageReceived"
        event = {
            "typeWebhook": event_type,
            "timestamp": int(datetime(2026, 10, 12, 14, 0, tzinfo=UTC).timestamp()),
            "idMessage": f"{transport.lower()}-{event_type}-{ident}",
            "senderData": {
                "chatId": f"{transport.lower()}-smoke-chat",
                "sender": "synthetic-account",
                "senderName": "Synthetic User",
                **({"chatType": "user"} if transport == "MAX" else {}),
            },
            "messageData": {
                "typeMessage": "textMessage",
                "textMessageData": {"textMessage": (
                    "Synthetic operator reply" if native else "Synthetic customer question"
                )},
            },
        }
        route = "/tg-gateway/callback/tg" if transport == "TG" else "/max-gateway/callback/max"
        return http_json(
            GATEWAYS[transport] + route, event,
            headers={"x-green-api-secret": auth},
        )[0]

