# API Connector Media M0: proposed contract freeze

**Status:** DRAFT / OWNER + MAINTAINER REVIEW REQUIRED. No runtime implementation, database migration, or production rollout is authorized by this document alone.

**Date:** 2026-10-25
**Base:** `amonrapmon/chatballs@feat/api-connector-upstream` (`8d65b79`)
**Related:** [adapter design PR #7](https://github.com/amonrapmon/chatballs-green-adapter/pull/7), [isolated media primitives PR #8](https://github.com/amonrapmon/chatballs-green-adapter/pull/8), [R&D-004 audit](https://github.com/amonrapmon/Chatballs-R-D/blob/docs/research-foundation/missions/round-004-private-adapter-boundary-audit.md).

## 1. Observed code, not assumptions

- The live Connector event path is mounted at `/api/v1/api-connector/organizations/{organization_public_id}/integrations/{integration_id}/events/` via `chatballs_backend/urls_app.py` and `api_connector/urls.py`. `ConnectorEventView` authenticates an Integration Bearer within `tenant_atomic`, and `parse_text_event` intentionally rejects media with 422.
- `ingest_inbound` creates one TEXT Message plus N FILE Messages; each FILE currently gets a suffix-derived `external_id`. `inbound_media._store_attachment` currently calls a native provider downloader and can downgrade a failed file to a text placeholder. Both behaviors are unsuitable as the Connector's atomic media contract.
- `Message.attachment`/`Message.audio` already use tenant-scoped storage paths. `DynamicTenantStorage` checks `organizations/{organization.public_id}/` and handles local/S3 selection. There must not be a second unguarded media store.
- `OrganizationStorageUsage`, `StorageReservation`, and `reserve_storage/finalize_storage/release_storage` exist. Their `storage_bytes` accounting is **not** a technical upload size or traffic quota: the tariff limit was removed (ADR-CHATBALLS-0042). Introduce explicit connector safeguards instead of claiming these helpers enforce a cap.
- The adapter's PR #8 has separate account-bound `DownloadFile`, bounded HTTPS downloader and multipart `SendFileByUpload`, but is not connected to workers and was not exercised against real GREEN-API.

## 2. Proposed decisions for approval

| ID | Proposed decision | Reason / compatibility boundary |
| --- | --- | --- |
| M0-A | Extend the **existing organization-UUID + Integration-ID URL family** with separate media endpoints; use the same rotated Integration Bearer and tenant resolution as `ConnectorEventView`. | Do not invent a second tenant selector or accept `source_id` as authorization. |
| M0-B | Use **single-shot streaming PUT** for the first increment. No chunks, Base64, public file URLs or Chatballs-to-provider downloads. Reserve → PUT → complete. | Small and reversible; resumability can be versioned later, without changing idempotent reserve. |
| M0-C | Store staged objects in a new **Integration-owned staging record** with private tenant storage and an opaque random `media_ref`. A ref never equals a provider URL, storage path, upload ID or message ID. | Clear lifecycle, expiry, ownership and same-Integration enforcement. |
| M0-D | Add **logical provider root** and ordered **message-part links** as dedicated persistence, not `:file:0` parsing. Key: (Integration, external_chat_id, external_message_id). | Supports caption + multiple files, closed/reopened conversations, audit and replay without coupling providers. |
| M0-E | Reuse `StorageReservation`/tenant storage for accounting, but enforce connector-specific per-file and aggregate staging bounds separately and transactionally. | Prevent concurrent reservation bursts and distinguish storage accounting from policy. |
| M0-F | **Media capability off by default**, explicit per-Integration opt-in only after both sides pass E2E; text and receipt routes unchanged. | Allows any mixed-version pair to keep reliable text behavior. |
| M0-G | Start with **one JPEG/PNG or PDF** plus optional caption and no native provider fallback. Other types and multiple-file manifests remain in the full schema, but fail closed until implemented. | Secure minimal M1/M2 proof without foreclosing full grouping. |

**Suggested initial policies, subject to explicit review:** 20 MiB max per file (existing `attachment_policy.MAX_FILE_BYTES`, not a protocol-wide guarantee); 100 MiB maximum outstanding staged bytes per Integration; reserve/partial TTL 1 hour; completed-but-unattached TTL 24 hours; content type allowlist `image/jpeg`, `image/png`, `application/pdf`. Enforce magic-byte checks appropriate to each type, reject mismatched/unsafe files, and retain restrictive download headers for documents. Use server-side limits, never client-supplied MIME/size alone. Any content-scanning limitations must be recorded and reviewed before media is enabled.

## 3. Proposed HTTP surface (additional, not live)

Prefix `/api/v1/api-connector/organizations/{organization_public_id}/integrations/{integration_id}/media/`:

| Verb and suffix | Request | Response |
| --- | --- | --- |
| `POST uploads/` | JSON: `request_id`, sanitized `filename`, `content_type`, integer `size_bytes`, hex `sha256` | `201` `{upload_id, expires_at}`; exact same request `200` with same upload ID; same ID/new manifest `409` |
| `PUT uploads/{upload_id}/content/` | Raw `application/octet-stream` bytes, hard streaming cap; fixed known size and hash are checked against reserve | `204` on durable bytes; repeat identical content `204`; changed bytes `409`. No redirects or file URL in response |
| `POST uploads/{upload_id}/complete/` | Empty JSON object; validate stored bytes, hash, true type and state | `200` `{media_ref, expires_at}`; idempotent exact replay returns the identical ref |
| `GET {media_ref}/content/` | **Future outbound only:** authenticated Integration plus bound immutable `command_id`, scoped authorization, short lease | Stream bytes, no unauthenticated URL; not part of M1 |

The first three endpoints inherit the exact Connector integration route auth, disabled/rotated-token behavior, 404 tenant isolation, and `Cache-Control: no-store`. Validate `Content-Length` early when present, but enforce the actual streamed count. Reject clients that try to change a completed object; never accept arbitrary `downloadUrl` as an upload input. A storage/DB error must not manufacture successful completion.

Recommended status codes: 400 malformed, 401 credentials, 403 inactive/feature disabled, 404 inaccessible ref/upload, 409 manifest/conflicting identity, 410 expired **only after scope check**, 413 over limit, 415 rejected media type, 422 unsupported kind, 429 budget exhausted, 503 transient storage unavailable. Do not echo file bytes, provider URLs, secret fragments or raw validation payloads in logs/errors.

**Idempotency identity:** `request_id` is generated and persisted by the adapter per source-event and file ordinal, bound to Integration and immutable metadata/hash. Reconnects and retries reuse it. Never regenerate when HTTP outcome is ambiguous.

## 4. Proposed persistence and consistency

### ConnectorMediaStage (new tenant-scoped record, not implemented)

Fields: `organization`, `integration`, `upload_id` (opaque), `request_id`, `request_fingerprint`, `media_ref` (separate opaque, nullable until complete), `state` (RESERVED/UPLOADED/COMPLETED/ATTACHED/EXPIRED), safe `filename`, declared and verified `content_type`, `declared_bytes`, `actual_bytes`, verified `sha256`, private `storage_key`, `expires_at`, `created_at`, `attached_at`.

Constraints: unique (integration, request_id), unique (media_ref) where non-null; index (integration, state, expires_at). Every read/write scopes by **authenticated** organization + Integration, not by guessing from `media_ref` alone. Tenant relationship validation must be enforced in application and database policy. Upload key is randomized under `organizations/{public_id}/connector-media/staging/`; no raw filename, source token or provider ID in the key.

### ConnectorMessageRoot and ConnectorMessagePart (new, not implemented)

- Root: `organization`, `integration`, `conversation`, `external_chat_id`, `external_message_id`, `event_fingerprint`, timestamps. Unique (integration, external_chat_id, external_message_id).
- Part: `organization`, `root`, `message` (FK existing `Message`), `ordinal` (0..N), `role` (caption/file/voice), optional `media_stage`. Unique (root, ordinal) and unique (message). Ordered parts are explicit, not inferred from generated external IDs.
- First event establishes root + immutable manifest. A later event with the same logical root but changed manifest is a conflict pending a separately designed edit/update protocol, **even if event IDs differ**. Exact event-ID replays use the current `InboxEvent` whole-envelope fingerprint and return its prior result.

Ingest must atomically mark staging as attached and create the root, Message rows, parts and inbox dedup inside one tenant transaction. It must **not** invoke `transports.download_file`, mutate global native behavior, or replace missing media with a text placeholder. Verify all refs, content ownership and manifest before creating the Message; any required ref unavailable aborts the entire event and remains recoverable from the adapter's durable raw event.

Database transactions cannot roll back object storage writes. Save verified staging bytes first under randomized tenant storage keys; make DB completion visible only when storage is durable. Copy/promote into canonical private attachment storage before the final DB transaction, retain source stage long enough to replay/reconcile, and garbage collect orphaned copies independently. Every deletion/accounting adjustment uses a locked lifecycle state and idempotency so storage bytes are neither leaked nor double decremented.

## 5. Proposed inbound event extension

Retain `chatballs.api-connector.event.v1`, `source_id=connection-{integration_id}`, authenticated route and current text envelope shape. With media enabled, allow `message.kind=file`, optional caption in `message.text`, and bounded ordered `attachments` containing `media_ref`, `ordinal`, `filename`, `content_type`, `size_bytes`, `sha256`. No `downloadUrl`, embedded bytes, or provider tokens. The envelope carries one provider root `external_message_id` (not separate derived message IDs).

Text-only payload validation and all existing receipt behavior must remain unchanged. When media is disabled, return typed 422 to the adapter without consuming staged refs, creating messages or reporting false 202.

## 6. Lifecycle and rollback evidence

1. Adapter resolves a provider file by its configured account, fetches within an approved destination policy, validates/records hash and stages using a stable `request_id`.
2. Chatballs reserves budget transactionally and writes bytes to private storage; completed ref is immutable.
3. Adapter emits its existing normalized event with only `media_ref`. All refs are checked for state/expiry/scope, then event + root + ordered children + attached stage become committed together.
4. Missing stage, corrupt bytes, disabled media or conflict: never acknowledge the raw event as delivered. Adapter keeps event recoverable/quarantined.
5. A scheduled **dry-run-first** cleanup discovers expired RESERVED/UPLOADED/COMPLETED stages without attached root; cleanup uses storage API and accounting checks. No cleanup against live rows/objects without separate approval.
6. Rollback: keep media capability disabled or revert route registration. No existing text message, receipt, operator command or Native Mirror is migrated or rewritten.

## 7. Acceptance and stop gates

Before any schema/runtime commit:
- Approve M0-A..G, especially root/part mapping and file limits.
- Confirm tenant RLS for both new models and migration dependencies on current branches.
- Prove identical reserve retry and same-ID/different-hash conflict; cross-Integration, wrong tenant, expired stage and token rotation fail closed.
- Prove streamed actual length, magic/MIME mismatch, invalid filename, concurrent over-budget uploads, storage write interruption and cleanup idempotence.
- Prove one caption + file yields a stable root and Message children; exact event replay no duplicate, changed event manifest `409`.
- Run only targeted Django tests and disposable Postgres migration rehearsal. CI success on adapter PR #8 does **not** verify Chatballs storage.
- Keep real provider, production DB, running workers, Native Mirror and original `intercom-gw` untouched.

## 8. Outstanding approval questions

1. Confirm the root + part **separate tables** rather than a group field on `Message`.
2. Approve the proposed `20 MiB / 100 MiB / 1h / 24h` technical policy and first media MIME matrix.
3. Approve one-shot PUT + scoped Bearer auth for M1. Outbound fetch remains a separate M3 security review.
4. Decide who runs expiration cleanup, how often, and whether an external malware scanning gate is mandatory before controlled Lab PDF attachment viewing.
5. Approve per-Integration feature gating and precise rollback semantics for mixed adapter / Chatballs versions.

**This document is a reviewable M0 output, not an approved implementation or proof of end-to-end media delivery.**
