# Chatballs API Connector v1 · Implementation-first wire contract

**Status: PRE-GA, based on working runtime** `feat/api-connector-events-v1-integration`.
This contract is for third-party adapters and integration tests. It is not a
claim that these endpoints are shipped by upstream Chatballs.

- [OpenAPI 3.1](./openapi.json): actual Chatballs ingress/attachment/admin routes
  and the independent adapter callback `/v1/commands`.
- [JSON Schema Draft 2020-12](./schema.json): strict event/receipt/command
  DTOs, including narrow supported variants and machine-readable enums.
- [Adapter developer guide](./ADAPTER_DEVELOPER_GUIDE.md): minimal third-party
  integration workflow, durable command ACK, replay, echo/receipt/media and
  safe provider-disconnected tests.
- [Standalone adapter verifier](./conformance/adapter_check.py): schema fixtures
  and opt-in **loopback-only** HTTP protocol checks, no Django/DB/provider.
- [Isolated conformance CI](../../.github/workflows/api-connector-conformance.yml):
  schema fixtures + loopback fake-adapter journal without backend services.
- [Executable conformance](../../apps/backend/chatballs/api_connector/test_contract_v1.py):
  cases checked against real Connector parsers and cross-references, not only
  syntactic examples.

## Two hosts and two different Bearer secrets

| Endpoint | Hosted by | Credentials | Function |
| --- | --- | --- | --- |
| `POST /api/v1/api-connector/organizations/{org_uuid}/integrations/{id}/events/` | Chatballs | Connector per-Integration Bearer | `message.created` (JSON text / multipart file), `message.observed_outgoing`, `message.echo`, and `receipt.v1` |
| `GET /api/v1/api-connector/organizations/{org_uuid}/integrations/{id}/commands/{command_uuid}/attachment/` | Chatballs | **Same Connector Bearer** | Authenticated file bytes for an existing native outbound command |
| `POST /api/v1/organizations/{org_uuid}/integrations/{id}/connector-credential/` | Chatballs admin | Authenticated session + CSRF + `integrations.manage` | Rotate adapter-to-Chatballs Bearer, return plaintext **once** |
| `POST /api/v1/organizations/{org_uuid}/integrations/{id}/connector-transport/` | Chatballs admin | Authenticated session + CSRF + `integrations.manage` | Configure outbound adapter HTTPS destination + **different** Bearer |
| `POST /v1/commands` | **Independent adapter** | Separate adapter-generated Bearer | Accept immutable Outbox command with 200/202 `{ "accepted": true, "id": command_id }` |

The organization UUID selects the tenant under RLS; it is **not** a secret.
`source_id` must be `connection-{integration_id}`. Do not send Green API
credentials, raw provider download URLs or provider secrets to Chatballs
event/command bodies. The native VK transport is independent of this API
Connector and does not migrate here.

## Wire semantics and current feature limits

- `event.v1 / message.created`: JSON text from `contact`, or one PNG, JPEG,
  PDF file with a manifest and binary multipart; the latter is gated by
  `connectorMediaInboundEnabled=true` (default false). No multi-file albums,
  threads, contact sharing, voice, HTML or replies yet.
- `event.v1 / message.observed_outgoing`: a **text** outgoing observed by an
  external adapter. Requires existing open conversation in this Integration
  and chat. Stored in native history as unattributed operator-like message
  (`author_user=NULL` and `connectorOrigin=EXTERNAL_OBSERVED`); never
  queues another send. Current AI pause policy still needs upstream review.
- `event.v1 / message.echo`: links a provider's own-send observation to a
  Chatballs command. It **does not** create another Message or advance the
  delivery state. Correlation must be source+chat+command UUID, or an existing
  persisted provider message ID. No provider ID takeover across observed/echo.
- `receipt.v1`: `PROVIDER_SENT`, `DELIVERED`, `FAILED`, scoped to command
  UUID. A `FAILED` receipt requires a short sanitized `failure_code`.
  Terminal statuses never regress. Receipt event IDs are deduplicated in an
  **independent namespace** from `event.v1` IDs.
- `command.v1`: one text message or one native file with `media[].ref=command`.
  The adapter fetches the file by scoped command UUID when outbound media is
  enabled (`connectorMediaOutboundEnabled=true`). A 200/202 ACK is only
  *durable adapter acceptance*, **never provider delivery**.

Limits: JSON ingress body 64 KiB, one multipart file max 20 MiB, multipart
envelope max file limit + 128 KiB, outbound command JSON 16 KiB. Binary
signatures, sha256, size, filenames, tenant permissions and state transitions
are validated at runtime; JSON Schema cannot prove byte-level integrity.

The adapter must persist event IDs and retry transient errors with the
**identical** payload/command UUID. `202` also means an exact replay was
safely deduplicated. Reusing an event ID with altered content returns
`409 id_conflict`. `409 unknown_command`/`unknown_conversation` is a
conditional retry case, not authorization to invent a new route.

## Why this differs from historical R&D

The [R&D proposal](https://github.com/amonrapmon/Chatballs-R-D/tree/docs/research-foundation/contracts/api-connector-v1)
was an architecture exploration. It specified legacy URLs without org UUID,
a separate receipt endpoint, staged uploads and alternate status/envelope
formats. Those were **not** the interfaces hardened in the running lab.
This canonical contract keeps the existing tenant UUID route, one typed event
webhook, native multipart and scoped command attachment GET. Missing R&D
capabilities remain backlog work (GEN-42 through GEN-57), not invented live
API routes.

## Validation and change policy

Run in the backend environment (requires `pip install 'jsonschema>=4.23,<5'`):

```sh
cd apps/backend
python -m pytest -q chatballs/api_connector/test_contract_v1.py
```

GitHub Actions also runs these assertions on a contract/Connector change and
continues to run existing PostgreSQL regressions. This is a versioned **v1**
wire shape and a **pre-GA** baseline. Any incompatible public contract change
needs an explicit migration/deprecation decision and new conformance fixtures
before a release, not just a markdown edit.
