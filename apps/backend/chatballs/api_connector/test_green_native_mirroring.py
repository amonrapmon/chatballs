"""Opt-in paired smoke using both real runtimes and local PostgreSQL databases."""

import json
import os
import socket
import subprocess
from contextlib import ExitStack, contextmanager
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from time import monotonic, sleep
from unittest.mock import patch
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import psycopg
import pytest
from django.utils import timezone

from chatballs.api_connector.outbound import CONNECTOR_OUTBOUND_REQUESTED, deliver_connector_command
from chatballs.conversations.models import Conversation, Message
from chatballs.events.models import OutboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.tenancy.context import TenantContext
from chatballs.testing import TenantAPIClient, system_tenant_context

CHAT_ID = "123456789"
REMOTE_AUTHOR = "987654321"
CALLBACK_SECRET = "synthetic-pair-webhook-token"
COMMAND_TOKEN = "synthetic-pair-command-token"


class SyntheticProvider(BaseHTTPRequestHandler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if "/sendMessage/" in self.path and request.get("chatId") == CHAT_ID:
            body = {"idMessage": "provider-own-send"}
        else:
            body = {}
        encoded = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):
        pass


@contextmanager
def local_provider():
    with ThreadingHTTPServer(("127.0.0.1", 0), SyntheticProvider) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(timeout=5)


@contextmanager
def node_process(root, entry, env, log):
    with log.open("wb") as stream:
        with subprocess.Popen(["node", str(root / entry)], stdout=stream, stderr=stream, env=env) as child:
            try:
                yield child
            finally:
                child.terminate()
                child.wait(timeout=5)


def wait_for(check):
    deadline = monotonic() + 12
    while monotonic() < deadline:
        try:
            if value := check():
                return value
        except (httpx.ConnectError, httpx.ConnectTimeout):
            pass
        sleep(0.1)
    pytest.fail("Paired operation timed out")


def local_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def start_adapter(stack, *, repo, db_url, platform, connection_id, webhook, token, chatballs_url, provider, logs, http):
    port = local_port()
    prefix = f"{platform.upper()}_GREEN_API_"
    source_id = f"fixture-{platform}-{uuid4().hex}"
    env = {
        **os.environ,
        "ADAPTER_MULTI_INSTANCE_ENABLED": "false",
        "APP_ENV": "test",
        "LOG_LEVEL": "warn",
        "PORT": str(port),
        "DB_URL": db_url,
        "SOURCE_ID": source_id,
        "SOURCE_LABEL": "Synthetic paired mirror",
        "CHATBALLS_BASE_URL": chatballs_url,
        "CHATBALLS_INTEGRATION_ID": str(connection_id),
        "CHATBALLS_INTEGRATION_SECRET": "synthetic-inherited-unused-token",
        "CHATBALLS_CONNECTOR_INGRESS_TOKEN": token,
        "CHATBALLS_CONNECTOR_COMMAND_TOKEN": COMMAND_TOKEN,
        "CHATBALLS_CONNECTOR_WEBHOOK_PATH": webhook,
        f"{prefix}ID_INSTANCE": str(connection_id),
        f"{prefix}TOKEN_INSTANCE": "synthetic-provider-token",
        f"{prefix}API_URL": provider,
        f"{prefix}MEDIA_URL": provider,
        f"{prefix}CALLBACK_ID": "synthetic-callback",
        f"{prefix}WEBHOOK_SECRET": CALLBACK_SECRET,
    }
    children = {
        entry: stack.enter_context(node_process(
            repo, f"{platform}-gateway/dist/{entry}.js", env,
            logs / f"{platform}-{connection_id}-{entry}.log",
        ))
        for entry in ("index", "delivery-worker", "status-projection-worker")
    }
    origin = f"http://127.0.0.1:{port}"

    def ready():
        for entry, child in children.items():
            if child.poll() is not None:
                pytest.fail(f"{platform} {entry} exited ({child.returncode}), see the local test log")
        return http.get(f"{origin}/healthz", timeout=1).status_code == 200

    wait_for(ready)
    return origin, source_id


def send_provider_callback(http, origin, platform, name, message_id, *, quote=None, timestamp=None):
    payload = {
        "typeWebhook": name,
        "timestamp": timestamp if timestamp is not None else int(timezone.now().timestamp()),
        "idMessage": message_id,
        "senderData": {"chatId": CHAT_ID, "sender": REMOTE_AUTHOR},
        "messageData": (
            {"typeMessage": "quotedMessage", "extendedTextMessageData": {"text": "Synthetic quote"},
             "quotedMessage": {"stanzaId": quote}}
            if quote else
            {"typeMessage": "textMessage", "textMessageData": {"textMessage": "Synthetic message"}}
        ),
    }
    result = http.post(
        f"{origin}/{platform}-gateway/callback/{platform}", json=payload,
        headers={"x-green-api-secret": CALLBACK_SECRET},
    )
    assert result.status_code == 200, result.status_code
    return payload


def wait_raw_processed(database, source_id, message_id):
    def processed():
        row = database.execute(
            """
            SELECT processing_status, error
              FROM raw_events
             WHERE source_id = %s AND event_name = 'outgoingMessageReceived'
               AND payload->>'idMessage' = %s
             ORDER BY id LIMIT 1
            """,
            (source_id, message_id),
        ).fetchone()
        if row and row[0] == "failed":
            pytest.fail(f"{message_id} failed in the adapter: {row[1]}")
        return row and row[0] == "processed"

    wait_for(processed)


@pytest.mark.skipif(
    not os.environ.get("CHATBALLS_TEST_GREEN_ADAPTER_ROOT") or not os.environ.get("CHATBALLS_TEST_GREEN_ADAPTER_DB"),
    reason="Requires a built adapter checkout and a disposable local adapter PostgreSQL database",
)
@pytest.mark.django_db(transaction=True)
def test_paired_green_native_mirroring(live_server, tmp_path):
    root = os.environ.get("CHATBALLS_TEST_GREEN_ADAPTER_ROOT")
    db_url = os.environ.get("CHATBALLS_TEST_GREEN_ADAPTER_DB")
    parsed = urlparse(db_url)
    assert parsed.hostname in {"127.0.0.1", "localhost"}
    assert parsed.path.startswith("/test_"), "Use a dedicated test_ adapter database"
    repo = Path(root)
    subprocess.run(
        ["node", str(repo / "db/dist/migrate.js")],
        env={**os.environ, "DB_URL": db_url}, cwd=repo, check=True, timeout=20,
    )
    result = bootstrap_owner(email="paired-connector@example.com", password="Synthetic-Paired-Test-Password!")
    org, owner = result.organization, result.owner
    client = TenantAPIClient()
    client.force_login(owner)

    def set_mirror(integration_id, enabled, *, at=None):
        with patch("chatballs.integrations.connector_settings.timezone.now", return_value=at or timezone.now()):
            response = client.patch(
                f"/api/v1/integrations/{integration_id}/",
                {"config": {"mirrorExternalOutgoingEnabled": enabled}}, format="json",
            )
        assert response.status_code == 200, response.status_code

    with (
        local_provider() as provider,
        httpx.Client(trust_env=False) as http,
        psycopg.connect(db_url, autocommit=True) as adapter_database,
    ):
        for platform in ("tg", "max"):
            with ExitStack() as stack:
                for instance in (1, 2):
                    integration = create_integration(
                        context=system_tenant_context(org),
                        data=IntegrationInput(provider=IntegrationProvider.API_CONNECTOR, name=f"{platform} {instance}"),
                    )
                    detail = f"/api/v1/integrations/{integration.pk}"
                    credential = client.post(f"{detail}/connector-credential/", {}, format="json")
                    assert credential.status_code == 201
                    origin, source_id = start_adapter(
                        stack, repo=repo, db_url=db_url, platform=platform, connection_id=integration.pk,
                        webhook=credential.data["webhookPath"], token=credential.data["token"],
                        chatballs_url=live_server.url, provider=provider, logs=tmp_path, http=http,
                    )
                    transport = client.post(f"{detail}/connector-transport/", {
                        "url": f"{origin}/v1/commands", "token": COMMAND_TOKEN,
                    }, format="json")
                    assert transport.status_code == 200, transport.data
                    send_provider_callback(http, origin, platform, "incomingMessageReceived", "provider-inbound")
                    conversation = wait_for(lambda connection=integration: Conversation.objects.filter(connection=connection).first())

                    def outgoing(message_id, *, quote=None, timestamp=None, origin=origin, platform=platform, source_id=source_id):
                        payload = send_provider_callback(
                            http, origin, platform, "outgoingMessageReceived", message_id,
                            quote=quote, timestamp=timestamp,
                        )
                        wait_raw_processed(adapter_database, source_id, message_id)
                        return payload

                    outgoing("provider-disabled")
                    mirrors = conversation.messages.filter(connector_origin="EXTERNAL_OBSERVED")
                    assert not mirrors.exists()

                    cutover = timezone.now() - timedelta(minutes=2)
                    set_mirror(integration.pk, True, at=cutover)
                    outgoing("provider-before-enable", timestamp=int((cutover - timedelta(minutes=1)).timestamp()))
                    assert not mirrors.exists()
                    observation = outgoing("provider-mirror", quote="provider-inbound")
                    mirrored = mirrors.get()
                    assert mirrored.author_user_id is None
                    assert mirrored.external_reply_to_id == "provider-inbound"
                    outgoing("provider-mirror", quote="provider-inbound", timestamp=observation["timestamp"])
                    assert mirrors.count() == 1

                    sent = client.post(f"/api/v1/conversations/{conversation.pk}/messages/", {
                        "text": "Own operator send",
                    }, format="json")
                    assert sent.status_code == 201, sent.data
                    message_id = sent.data["message"]["id"]
                    outbox = OutboxEvent.objects.get(
                        event_type=CONNECTOR_OUTBOUND_REQUESTED, payload__message_id=message_id,
                    )
                    deliver_connector_command(outbox.payload, TenantContext.for_resource(org))
                    wait_for(lambda pk=message_id: Message.objects.filter(
                        pk=pk, connector_delivery__providerMessageId="provider-own-send",
                    ).exists())
                    outgoing("provider-own-send")
                    assert mirrors.count() == 1

                    set_mirror(integration.pk, False)
                    outgoing("provider-disabled-again")
                    assert mirrors.count() == 1
