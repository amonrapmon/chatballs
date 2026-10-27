# API Connector v1: text ingress, operator outbound, provider receipts

**Status: bidirectional text up to an independent adapter; provider delivery is asserted only by authenticated receipts.**

- Admin creates an API_CONNECTOR integration, without an AI agent if desired.
- Admin calls `POST /api/v1/organizations/{organization_public_id}/integrations/{id}/connector-credential/` (normal logged-in integrations.manage permission/CSRF) to issue or rotate a key. Response contains `token` **once**, `sourceId`, `webhookPath`. Keep token only in secure adapter configuration; rotating immediately revokes old key. No Green API token is accepted by this endpoint.
- Adapter sends `POST {webhookPath}`, `Authorization: Bearer {token}`, JSON with the `chatballs.api-connector.event.v1` envelope. Expected `source_id` equals returned `sourceId` (`connection-{id}`). Full canonical event fingerprint and `event.id` are used for idempotency; same ID with different content returns HTTP 409. Operator-only Inbox uses shared `ingest_inbound` service. AI replies remain disabled for this connector. Operator replies require a configured outbound adapter; otherwise they return HTTP 409.
- Route includes public organization UUID so tenant authorization can be resolved via existing security-barrier organization directory **before** the database's row-level-security context is opened. The UUID is not an authorization credential.
- **HTTP 202** means the normalized text event has been processed and committed to Chatballs, including replay acceptance; it does **not** assert external provider delivery.

**Not implemented:** media staging/streaming, message-root mapping across multiple events, AI outbound, external observed outgoing, own-send echoes, capability discovery, token distribution through UI, and provider delivery to a real messenger. Unsupported v1 event families, media, voice, HTML, replies, contacts and actions return typed 422 without a fake success.

The [R&D protocol](https://github.com/amonrapmon/Chatballs-R-D/tree/docs/research-foundation/contracts/api-connector-v1) describes the *target* end state; its proposed URL without organization UUID is superseded by this live source-routing choice for the first milestone, pending final maintainer review. Keep `intercom-gw` private and independent.


## Second milestone: operator text outbound

An admin with `integrations.manage` configures the independent command receiver via
`POST /api/v1/integrations/{id}/connector-transport/` with JSON
`{"url":"https://adapter.example/v1/commands","token":"adapter-generated-bearer"}`.
The URL has a fixed `/v1/commands` path and no URL credentials or query. HTTPS is
required except loopback HTTP for local fake-adapter testing. The adapter Bearer
is stored encrypted and never included in the Integration payload or OutboxEvent.

With this configuration, a human operator reply is saved as `QUEUED` together
with a durable, source-scoped `chatballs.api-connector.command.v1` outbox
event. The existing worker sends the immutable command to the adapter.
HTTP 202 (new) or 200 (idempotent replay) advances message state to
`ADAPTER_ACCEPTED`. Timeout/5xx/redirects never claim acceptance and are
retried by the established outbox worker with the identical `command_id`.
The API exposes `connectorDelivery` in the message payload.

**Important:** `ADAPTER_ACCEPTED` does not mean provider-sent or customer-delivered.
Automatic retry controls after dead letter, media, AI outbound and real Green API
transport remain separate follow-up milestones.


## Third milestone: authenticated provider delivery receipts

The independent adapter sends `POST {webhookPath}`, with the SAME inbound
per-integration `Authorization: Bearer {token}` credential obtained from
`connector-credential/`, plus this body:

```json
{
  "schema": "chatballs.api-connector.receipt.v1",
  "source_id": "connection-2",
  "event": {"id": "receipt-1", "occurred_at": "2026-10-23T17:30:00Z"},
  "command_id": "66778171-9aa2-58e9-b2c4-9fc96c1bed4d",
  "status": "PROVIDER_SENT",
  "provider_message_id": "remote-message-1"
}
```

`status` is one of `PROVIDER_SENT`, `DELIVERED`, or `FAILED`. For FAILED,
the adapter **must** provide a short machine-readable `failure_code`
(e.g. `recipient_unavailable`); arbitrary provider exception text and
sensitive payloads are not accepted. `provider_message_id` is optional.

- **HTTP 202** `{"accepted":true,"id":"receipt-1"}` means the event was
  applied or safely deduplicated. It does not independently verify the provider.
- **HTTP 409** `unknown_command` means the command was not found in *that*
  Integration and tenant; retry the same event after command creation.
  `source_mismatch` and `id_conflict` are not retryable as-is.
- **HTTP 401/403** means invalid or inactive connector credentials/config.
- **HTTP 400/422** means malformed or unsupported receipts.

The exact event ID + canonical payload SHA256 is deduplicated in InboxEvent.
Reusing an event ID with different content returns 409. All updates lock the
corresponding operator message row. States only progress forward:
`QUEUED → ADAPTER_ACCEPTED → PROVIDER_SENT → DELIVERED`;
`FAILED` and `DELIVERED` are terminal. Events can skip intermediate states,
and late lower-ranked status/HTTP ACKs cannot downgrade them. The trusted
adapter is responsible for authentic provider callbacks, persisting and
retrying receipt events, and stable command / event identities.

The `connectorDelivery` object in the message API reflects persisted state,
timestamp `updatedAt`, optional `providerMessageId`, and optional
`failureCode`. This milestone does not add new operator UI badges or
retry controls. Legacy queued messages from exhausted outbound retries are
not yet projected to FAILED; that requires a separate outbox terminal-failure
hook.

## Opt-in native media ingress (M1, initial pilot)

The existing Connector webhook `POST {webhookPath}` now accepts **one** photo or PDF, using `multipart/form-data` with `Authorization: Bearer {connector-token}`. Its **JSON text and receipt endpoints remain unchanged**.

- Integration-side capability switch: `config.connectorMediaInboundEnabled = true`. Off by default. This is a backend/Lab switch, not an exposed integration UI setting.
- Form field `event`: the existing `chatballs.api-connector.event.v1` JSON envelope. Set `message.kind = "file"`, `message.text` to the optional caption (empty string is valid), and exactly one attachment manifest `{"filename":"photo.png","content_type":"image/png","size_bytes":69,"sha256":"<lowercase-sha256-of-binary>"}`.
- Form field `file`: binary bytes. Filename and MIME must agree with the manifest. Initial content matrix: PNG, JPEG and PDF, max 20 MiB (current native `attachment_policy.MAX_FILE_BYTES`).
- Adapter resolves and downloads from its provider *before* this call. **Do not** send a provider URL, public download link, `media_ref`, Base64, or provider credentials to Chatballs.
- Chatballs validates hash/length/content signature, then creates ordinary native `InboundFile(content=...)` / `InboundMessage(files=...)` and passes them through `ingest_inbound`; file storage and operator UI are the normal `Message.attachment` path.
- The original event ID must remain stable across retries. Exact replay is accepted with no second message; changed event manifest under the same event ID returns `409 id_conflict`. The adapter must retain failed/unsupported events; `202` is never a promise of provider delivery.
- Files are only admitted after resolving and authorizing the URL's organization and Integration. Invalid token: `401`, disabled: `403`, media not enabled: `422`. Multipart total body is bounded before parsing and actual file bytes are checked after reading.
- This limited pilot does not implement multi-file albums, cross-event provider-root grouping, voice/video or outbound operator attachments. Those must reuse Chatballs core and need separate tests/review, not Connector-specific storage or tables.

No migrations, additional media storage, cleanup worker or Native Mirror changes are introduced in M1.


## External observed outgoing text (initial GEN-47 slice)

The adapter can send an event observed **outside Chatballs** to the existing
`POST {webhookPath}` with its Integration-scoped Bearer token:

```json
{
  "schema": "chatballs.api-connector.event.v1",
  "source_id": "connection-2",
  "event": {
    "id": "observed-out-1",
    "type": "message.observed_outgoing",
    "occurred_at": "2026-10-27T12:00:00Z"
  },
  "conversation": {"external_chat_id": "provider-chat-1"},
  "sender": {"external_user_id": "remote-account-1"},
  "message": {
    "external_message_id": "remote-message-1",
    "direction": "outbound",
    "origin": "external_observed",
    "actor": "unknown",
    "kind": "text",
    "text": "Ответ из приложения мессенджера",
    "attachments": []
  }
}
```

This first slice only handles plain text and an **already known OPEN conversation**
bound to exactly the same Integration and external chat. Unknown conversation:
`409 unknown_conversation`, with no event ID consumed so the adapter may
retry after an actual inbound created the route. There is no contact lookup by
an untrusted remote actor, no automatic new contact/conversation creation.

The message is saved as a native `Message(author_type=OPERATOR, author_user=NULL)`
with `connector_origin=EXTERNAL_OBSERVED`. The history API includes
`connectorOrigin`. This records an **unattributed external response**, not a
claim that a Chatballs employee sent it. The supplied sender's remote ID is
validated but never mapped to a local employee. No outbound command is enqueued
and no duplicate Message is created when the same provider message is replayed.

If AI controlled the conversation at receipt time, the observed external
message moves it to the native `PAUSED` queue, avoiding a competing future AI
reply. Existing HUMAN assignment is preserved but does **not** attribute
the external response to that assigned employee. Repeated events do not repeat
queue transitions. This initial state policy needs explicit review with the
upstream Native Mirror lifecycle before GA.

Exact event replay responds `202`; changed event with the same event ID or a
provider message-ID collision is `409`. If the provider message ID belongs to
an outbound Chatballs command, the adapter must emit `message.echo`, not
`message.observed_outgoing` (`409 echo_expected` when detectable).

Not yet supported: observed outgoing media, replies/threads, actor identity
verification, closed-conversation history import and cross-event media roots.
The final wire contract will be versioned in GEN-43/GEN-44 with conformance.
