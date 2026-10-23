# API Connector v1: first executable milestone

**Status: text ingress only. Not a functioning bidirectional messenger.**

- Admin creates an API_CONNECTOR integration, without an AI agent if desired.
- Admin calls `POST /api/v1/organizations/{organization_public_id}/integrations/{id}/connector-credential/` (normal logged-in integrations.manage permission/CSRF) to issue or rotate a key. Response contains `token` **once**, `sourceId`, `webhookPath`. Keep token only in secure adapter configuration; rotating immediately revokes old key. No Green API token is accepted by this endpoint.
- Adapter sends `POST {webhookPath}`, `Authorization: Bearer {token}`, JSON with the `chatballs.api-connector.event.v1` envelope. Expected `source_id` equals returned `sourceId` (`connection-{id}`). Full canonical event fingerprint and `event.id` are used for idempotency; same ID with different content returns HTTP 409. Operator-only Inbox uses shared `ingest_inbound` service. Even when an AI agent is configured, its turn is not triggered until outbound delivery exists; operator text sends return HTTP 409 rather than leaving false-sent history.
- Route includes public organization UUID so tenant authorization can be resolved via existing security-barrier organization directory **before** the database's row-level-security context is opened. The UUID is not an authorization credential.
- **HTTP 202** means the normalized text event has been processed and committed to Chatballs, including replay acceptance; it does **not** assert external provider delivery.

**Not implemented:** media staging/streaming, message-root mapping across multiple events, operator/AI outbound commands, delivery receipts, external observed outgoing, own-send echoes, capability discovery or token distribution through UI. Unsupported v1 event families, media, voice, HTML, replies, contacts and actions return typed 422 without a fake success.

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
Provider delivery receipts, automatic retry controls after dead letter, media,
AI outbound and real Green API transport remain separate follow-up milestones.
