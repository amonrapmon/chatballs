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
