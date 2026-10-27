# Build an independent Chatballs API Connector v1 adapter

**Developer preview · implementation-first · pre-GA.** This guide covers the
working v1 contract on branch `feat/api-connector-events-v1-integration`,
not an upstream Chatballs release. It is for Telegram/MAX GREEN-API adapters
and other third-party transports. **Native VK remains native** and is not a
Connector migration target.

The adapter is a small process: it transforms provider events into Chatballs
DTOs, hosts one authenticated command receiver, persists retries/identities,
and reports delivery evidence. It must NOT reimplement Chatballs' conversation
storage, AI state, assignment queues, or media library.

## 1. Choose the right components

```text
Provider (Telegram/MAX/other)
      │ provider-specific callbacks and media downloads
      ▼
Independent adapter: normalization + durable journal
      ├── POST event.v1 / receipt.v1 ─────► Chatballs /events/ (Connector Bearer A)
      ▲
      └── POST /v1/commands ◄───────────── Chatballs Outbox (adapter Bearer B)
                       │
                       └── GET /commands/{command_id}/attachment/ from Chatballs
                           (Connector Bearer A, gated outbound media)
```

`Bearer A` is issued **by Chatballs**, once per Integration, through the
authenticated `connector-credential/` admin endpoint. `Bearer B` is generated
**by your adapter** and configured in Chatballs `connector-transport/`; never
reuse it as Bearer A. Keep the secrets out of log lines, event bodies, durable
Outbox payloads and crash diagnostics.

The `organization_public_id` and `integration_id` select the route but
are **not authentication tokens**. `source_id=connection-{integration_id}`
is the same stable value throughout that Integration.

[OpenAPI 3.1](./openapi.json) · [JSON Schema 2020-12](./schema.json) ·
[Supported runtime and security limits](./README.md)

## 2. Register and configure the adapter

1. An authorized Chatballs administrator creates an `API_CONNECTOR`
   Integration. No AI agent is required.
2. The administrator issues/rotates the inbound credential through
   `POST /api/v1/organizations/{org_uuid}/integrations/{id}/connector-credential/`
   under the **existing authenticated Chatballs admin session + CSRF**.
   Store `token` securely; the response returns it once. Also store
   `webhookPath` and `sourceId`.
3. Deploy your command receiver at **exactly** `POST /v1/commands`. Use
   HTTPS in production (loopback HTTP is only for local lab tests). Generate
   a *different* adapter-secret Bearer B.
4. The administrator configures
   `POST /api/v1/organizations/{org_uuid}/integrations/{id}/connector-transport/`
   with `{"url":"https://adapter.example/v1/commands","token":"<Bearer B>"}`,
   under the same admin session/permission.
5. Ensure the provider-side subscription and durable journal exist **before**
   accepting new traffic.

Do not put provider API tokens into Chatballs or expose the adapter command
receiver to the internet without TLS and authentication.

## 3. Inbound: provider → Chatballs

Transform the provider's incoming text into `message.created`:

```json
{
  "schema": "chatballs.api-connector.event.v1",
  "source_id": "connection-2",
  "event": {
    "id": "provider-update-1001",
    "type": "message.created",
    "occurred_at": "2026-10-27T12:00:00Z"
  },
  "conversation": {"external_chat_id": "chat-17"},
  "sender": {"external_user_id": "contact-42", "display_name": "Guest"},
  "message": {
    "external_message_id": "provider-message-99",
    "direction": "inbound",
    "origin": "external_observed",
    "actor": "contact",
    "kind": "text",
    "text": "Hello",
    "attachments": []
  }
}
```

Send JSON `POST {webhookPath}` to the Chatballs host with
`Authorization: Bearer <Bearer A>` and `Content-Type: application/json`.
Use stable provider chat/user/message IDs **within that Integration**.
Generate and persist a stable `event.id` that survives callbacks, network
timeouts and restarts. A retry must contain the **same canonical content**,
not just the same ID. `202` means persisted/deduplicated, **not delivered to
a guest**. Changed content under an existing ID yields `409 id_conflict`.

For inbound PNG, JPEG, or PDF files, download binary bytes **inside your
adapter**. POST multipart with exactly one `event` field containing the
JSON `message.created` envelope (`kind=file`, one attachment manifest:
`filename`, `content_type`, `size_bytes`, lower-case `sha256`) and one
`file` binary part. Native limit is 20 MiB per file and upload is
**disabled by default** until `connectorMediaInboundEnabled=true` is enabled.
Never send URLs, Base64, arbitrary file types or provider credentials instead
of bytes. Multiple files, voice, video, GIF and replies are not v1 features.

## 4. Outbound: Chatballs → adapter

Chatballs creates an immutable `command.v1` in its Outbox. It sends that
command to your authenticated `POST /v1/commands`:

```json
{
  "schema": "chatballs.api-connector.command.v1",
  "source_id": "connection-2",
  "command_id": "66778171-9aa2-58e9-b2c4-9fc96c1bed4d",
  "recipient": {
    "external_chat_id": "chat-17",
    "external_user_id": "contact-42"
  },
  "route_version": "source-scoped-route-v1",
  "created_at": "2026-10-27T12:01:00+00:00",
  "message": {"kind": "text", "text": "Reply from operator", "media": []}
}
```

**Do not send to the provider and then casually return `202`.** First
authenticate Bearer B, verify the schema and source, persist an immutable
fingerprint keyed by `command_id` in a durable journal, and atomically reserve
the command for provider delivery. Then and only then respond with
`202 {"accepted":true,"id":"<same command_id>"}`. Identical replay responds
`200` with the same ACK and **does not queue another provider send**.
Changed payload under the same UUID must fail, typically `409`.
Never treat acceptance as provider delivery. Transport timeouts, connection
loss, redirects and failures can cause Chatballs to retry the same command.
Preserve command identity across retries and adapter restarts.

For `kind=file`, the command carries one `message.media[]` manifest with
`ref=command`, filename, MIME type, size and SHA256. After authenticating and
durably accepting, retrieve its bytes using **Bearer A** at
`GET /api/v1/api-connector/organizations/{org_uuid}/integrations/{id}/commands/{command_id}/attachment/`,
validate the manifest and then upload using the provider's native mechanism.
Do not invent a public media URL; this GET uses native Chatballs storage and
is guarded by `connectorMediaOutboundEnabled=true`.

## 5. Receipt and echo are not interchangeable

After observing a real provider outcome, the adapter can POST a
`receipt.v1` to the same Chatballs `{webhookPath}` (Bearer A), with the
original `command_id` and an independent event ID:

```json
{
  "schema": "chatballs.api-connector.receipt.v1",
  "source_id": "connection-2",
  "event": {"id": "provider-status-1001", "occurred_at": "2026-10-27T12:02:00Z"},
  "command_id": "66778171-9aa2-58e9-b2c4-9fc96c1bed4d",
  "status": "PROVIDER_SENT",
  "provider_message_id": "provider-msg-555"
}
```

Allowed receipts: `PROVIDER_SENT`, `DELIVERED`, or `FAILED`. A
`FAILED` event requires a short, sanitized `failure_code`, never a raw
provider exception with message text or secrets. Receipt statuses are
monotone; `DELIVERED` and `FAILED` are terminal.

If the provider later mirrors an outbound Chatballs-originated command, emit
`message.echo` correlating the *existing* command with its provider message
ID. Echo is not delivery evidence and must not create a second message.
If a human wrote **outside** Chatballs and no Chatballs command exists,
emit `message.observed_outgoing` with `actor=unknown`. This stores a
plain-text unattributed outgoing reply in the existing open conversation.
Do not forge a Chatballs staff ID or silently change `observed_outgoing`
into an echo.

## 6. Error and retry policy

| Result | Required adapter behavior |
| --- | --- |
| Chatballs `202` | Remove/mark the **identical** event from durable retry queue |
| `401/403` | Stop sending; fix credential/Integration status, no blind retries |
| `400/413/422` | Quarantine payload; fix representation/capability, not infinite retry |
| `409 id_conflict` or `source_mismatch` | Quarantine and investigate collision/route |
| `409 unknown_command` or `unknown_conversation` | Retain original event for a bounded conditional retry, preserving ID/payload |
| `503`, HTTP `5xx`, network ambiguity | Backoff with jitter and resend **identical** event; no invented ACK |
| Adapter HTTP `200/202` for command | Accept only with valid JSON `{"accepted":true,"id":command_id}`; journal must already be durable |

To avoid duplicate sends after provider timeouts, maintain separate durable
`command_id` → delivery-attempt/provider-ID state. When a provider has no
idempotency key and a send outcome is unknown, prefer explicit recovery over
blind repeated provider sends. Do not advertise `DELIVERED` from a callback
HTTP acknowledgment or from command acceptance.

## 7. Verify before connecting a real provider

Install Python 3.12+ and `jsonschema>=4.23,<5`. The standalone verifier uses
**no Django, Postgres, Chatballs secret, provider API, or production network**.

Offline wire fixtures only:

```sh
python -m pip install "jsonschema>=4.23,<5"
python contracts/api-connector-v1/conformance/adapter_check.py --json
```

For a provider-**disconnected**, sandbox command receiver that listens on
loopback, run HTTP conformance tests. They send synthetic commands and expect
correct authentication, first-acceptance, idempotent replay, conflicting replay
and source validation. The verifier **refuses all non-loopback URLs**. For a
remote sandbox, use an SSH tunnel to a loopback port rather than disabling the
guard.

```sh
export ADAPTER_CONFORMANCE_TOKEN="a-synthetic-sandbox-bearer-at-least-16-chars"
python contracts/api-connector-v1/conformance/adapter_check.py \
  --adapter-url http://127.0.0.1:9081/v1/commands \
  --source-id connection-2 --json
```

The secret is read from an environment variable, not a command-line flag or
printed output. Use an ephemeral sandbox credential, **never a live provider
credential**. To run the provider-free local reference test suite:

```sh
python -m unittest discover \
  -s contracts/api-connector-v1/conformance -p 'test_*.py' -v
```

It runs the existing stdlib-only loopback fake adapter in a subprocess-like
isolation from Chatballs imports, with a local journal. The CI workflow
`api-connector-conformance.yml` executes these tests without DB services.

**Passing these checks means baseline HTTP/DTO conformance, not production
readiness.** The verifier does not cover crash/restart replay, provider
authentication, provider delivery, media E2E, tenant isolation in a live
Chatballs instance, TLS termination, rate limiting, AI lifecycle, or real
MAX/Telegram provider behaviors. Those require separate staging E2E and
security review before GA.

## 8. Minimum adapter project checklist

- [ ] Provider-specific event normalizer with durable event ID and route mapping
- [ ] Verified `/v1/commands` endpoint with Bearer B, stable UUID, durable journal
- [ ] Correct `200/202` durable ACK and `409` on modified replay
- [ ] Outbox worker with explicit ambiguous-send recovery
- [ ] Separate `receipt.v1` and `message.echo` flows
- [ ] `observed_outgoing` only for truly external human/outgoing messages
- [ ] Conditional media capabilities and secure attachment fetch
- [ ] Secrets redacted in logs, backup and metrics; integration-scoped trust
- [ ] Offline + loopback conformance green, then gated staging provider E2E

Do **not** claim general capability discovery, AI outbound, albums, contact
shares, replies, voice/video, read receipts or a universal SDK is implemented
until those features have explicit runtime support and contract tests.
