# API Connector Media M0: thin native-ingress bridge

**Status:** DRAFT / REVIEW REQUIRED (2026-10-25). This is an architecture correction to PR #10, **not** a shipped runtime or permission to change production.

**Baseline:** `amonrapmon/chatballs@feat/api-connector-upstream`, existing text/receipt Connector v1.
**Related:** [R&D-003 full target contract](https://github.com/amonrapmon/Chatballs-R-D/blob/docs/research-foundation/research/02-message-lifecycle/round-003-api-connector-v1-contract.md), [R&D-004 adapter boundary](https://github.com/amonrapmon/Chatballs-R-D/blob/docs/research-foundation/missions/round-004-private-adapter-boundary-audit.md), [adapter PR #7](https://github.com/amonrapmon/chatballs-green-adapter/pull/7) and [provider media primitives PR #8](https://github.com/amonrapmon/chatballs-green-adapter/pull/8).

## Architectural rule

> API Connector exposes native Chatballs behavior to external adapters. It must **not** reimplement the attachment system, message models, inbox, media storage, provider workers, or native outgoing routes.

The adapter owns provider URLs, auth, downloads, normalized event identity and retries. Connector only authenticates the Integration, validates the boundary payload, converts it to the **existing** domain DTO, and invokes the **existing** domain ingest. Chatballs core keeps owning canonical Message, attachments, conversations, UI, audit and its normal storage.

Existing native application service entry points are the reuse target, **not** Telegram/MAX-specific HTTP URLs or their provider credentials.

## Source-verified reuse inventory

| Code | Observed existing capability | Decision |
| --- | --- | --- |
| `conversations/transports/base.py` | `InboundFile.content: bytes`, `InboundMessage.files`, `InboundMessage.voice_content` | Reuse DTOs; no second file payload model. |
| `conversations/transports/__init__.py` | `download_file(...)` returns `inbound_file.content` immediately if present; `download_voice(...)` accepts `voice_content` | Provide verified bytes; no Chatballs request to GREEN-API. |
| `conversations/ingest.py` | `ingest_inbound(..., connector_event_id, connector_fingerprint)` already dedups source events and creates TEXT caption + ordered FILE children using native Message model | Invoke it once after complete media validation. No ConnectorMessageRoot/Part. |
| `conversations/inbound_media.py` | Native `_store_attachment` persists `Message.attachment` through `ContentFile` | Reuse; do not add a parallel storage layer. |
| `conversations/message_models.py` and `upload_paths.py` | `Message.attachment`, name, MIME, size and organization-scoped file paths | No new attachment tables or separate file store. |
| `tenancy/storage_backends.py` | Tenant key guard and dynamic local/S3 storage | Existing storage owns bytes. |
| `conversations/attachment_policy.py` | `validate_upload`, 20 MiB current file cap, blocked extension policy | Reuse current policy; the Connector boundary still verifies upload bytes vs declared hash/size/type. |
| `conversations/inbound_dedup.py` | `InboxEvent` dedup by scoped event ID + complete event fingerprint | Preserve existing replay/conflict semantics. |
| `api_connector/{views,urls,payloads}.py` | Integration Bearer, tenant-bound event route and strict JSON-only text parser | Extend only the ingress protocol for media, guarded by capability. Do not change existing JSON text/receipt processing. |

**Important caveats:** `ingest_inbound` currently uses derived `:file:{index}` external IDs to represent native Message rows, and native `_store_attachment` can turn a *download failure* into a placeholder. This proposed first slice passes nonempty bytes, so it never asks Chatballs to download provider data. It does **not** claim durable cross-event grouping or arbitrary partial-file recovery. Existing `StorageReservation` is bookkeeping without a tariff cap; do not build another quota system or claim it bounds Connector traffic. Native storage writes are not automatically rolled back by database transactions: test and handle file-orphan failure paths before enabling traffic.

## M1: narrow wire extension with no media staging

### Reuse the **same** Connector event URL

`POST /api/v1/api-connector/organizations/{organization_public_id}/integrations/{integration_id}/events/`

Current `application/json` behavior stays **byte-for-byte compatible** and text-only. Add opt-in `multipart/form-data` processing **at the same route** for one media event:

- text form part `event`: a UTF-8 JSON string containing the current `chatballs.api-connector.event.v1` envelope; `message.kind = "file"`, optional `message.text` caption, exactly one `attachments[]` manifest;
- binary part `file`: upload body, **not** URL, Base64, or a persistent `media_ref`;
- manifest: `filename`, `content_type`, `size_bytes`, lower-case hex `sha256`. No `downloadUrl`, upstream provider ID, Chatballs file path or arbitrary file-field selector. The file bytes are scoped to this request.
- only image/jpeg, image/png and application/pdf in the **initial** limited matrix; other media formats remain not implemented. The existing file extension/size policy remains a lower-level shared gate.

No additional `/media/uploads` URLs, `ConnectorMediaStage`, `ConnectorMessageRoot`, `ConnectorMessagePart`, `media_ref` resolution, second garbage collector, or migration in M1.

This **single-request wire shape is a proposed, intentionally smaller alternative** to R&D-003's staged-`media_ref` full-v1 design. It must be ratified as a versioned/capability-gated media profile; do not silently pretend that multipart is the already-approved full R&D-003 protocol.

### Validation and invocation

1. Reject excessive `Content-Length` early; **authenticate and resolve organization + Integration before parsing multipart or reading file bytes**. Use the current Bearer rotation, integration-active and tenant route rules.
2. Allow multipart only with an explicit per-Integration media capability, off by default. Use Django/DRF upload handlers and a hard aggregate request/file cap; enforce **actual streamed size** and the native attachment policy. Do not read an unlimited request into memory or use `request._request.body` for multipart.
3. Parse the JSON `event` part using the existing duplicate-key/non-finite protections and a narrow `parse_media_event` extension. Enforce current inbound sender/route constraints, one attachment, optional caption and immutable event identity. Preserve `parse_text_event` behavior.
4. Normalize and validate `safe_filename`, declared MIME, actual size and SHA-256 of the uploaded bytes; reject executable/blocked suffixes and MIME/type confusion under the chosen common policy. A filename or `Content-Type` alone does not prove a safe file.
5. Construct native `InboundFile(name=..., content_type=..., size=..., content=validated_bytes, is_image=...)`, then native `InboundMessage(..., text=caption, files=(file,))`; supply `connector_event_id` and the **complete canonical event fingerprint** to the existing `ingest_inbound` inside `tenant_atomic`.
6. Chatballs creates the canonical caption TEXT (if any) and FILE Message(s), using the existing `Message.attachment` and local/S3 storage. Reply `202` only when native ingest and its database transaction succeed.
7. **Exact event replay** with identical manifest remains accepted without creating another Message. Same `event.id` with altered media hash/filename/route returns `409 id_conflict`. The adapter must retain a stable event ID across retries for a provider root; this initial slice **does not guarantee dedup when a provider emits the same root under a new event ID**.
8. Failure before canonical ingest creates no message. Storage errors during ingest must propagate, not be falsely transformed into a successfully processed media event; if native storage wrote an object but the DB fails, the implementation needs a narrow cleanup/compensation strategy that reuses the storage API. No global native ingestion rewrite in M1.

Authentication continues to derive organization/Integration from URL + Bearer, never the envelope's `source_id`. Untrusted multipart metadata must not select a tenant or outgoing route. Raw bytes and provider details never reach logs or responses.

### Compatibility gates

- JSON text and receipts: **unchanged**; repeat all current focused `api_connector` tests.
- Media flag off or old Chatballs: typed unsupported `422` (no fake accepted file). The adapter persists and retries/quarantines the original provider event.
- Mixed deployment: media-capable Chatballs + old adapter keeps text; media-capable adapter + old Chatballs stays text until negotiated and enabled.
- No changes to Native Mirror, original `intercom-gw`, existing Telegram/MAX worker implementation or production routing.

## Why no group model in M1?

Native `ingest_inbound` already fans a provider event into caption + file Message rows, while `InboxEvent` fingerprints the **whole event**. For an **exactly one-event/one-provider-root/single-attachment** pilot, this is sufficient to reuse native behavior. Do not infer an extra logical group from `:file:0`, and do not add root/part schema merely to cover a hypothetical cross-event case.

**Known boundary:** a second *different* event ID for the same provider root is not fully handled by native event dedup. Before enabling albums, edits, segmented provider media or multi-event roots, prove whether the adapter can guarantee one stable logical event ID or propose a **generic Chatballs core enhancement** applicable to native channels, not Connector-only tables.

## Outbound attachment: same principle, later milestone

The operator-facing `ConversationAttachmentView` already owns upload validation, claim, message and file persistence, but currently `transports.supports_file_send()` excludes `API_CONNECTOR` and uses synchronous provider send. Do **not** route outbound files through a native Telegram/MAX URL or clone a second operator composer.

A later change should share the same operator upload/claim/attachment service, then enqueue the **existing durable Connector outbound command** with immutable attachment identity, per-Integration authenticated byte-fetch (or another reviewed private transfer method), and provider-specific `SendFileByUpload` in the adapter. No public Chatballs media URL, no false `DELIVERED` from an HTTP ACK. Outbound bytes-fetch design is not required for M1 inbound.

## Small implementation plan (after this M0 review)

**M1a:** focused parsing/authorization plus multipart ingestion of one PNG/JPEG/PDF and optional caption, calling native DTO + `ingest_inbound`. No new model/migration/UI.

**M1b:** focused Django endpoint/DB tests of idempotent replay, changed hash conflict, invalid/empty/oversized/unsafe file, incorrect tenant/Integration, rotated token, disabled capability and native storage errors. Test with disposable Postgres and private test-media storage. Verify file cleanup on failure and tenant storage isolation.

**M2:** adapt GREEN-API inbound worker to existing tested download primitive and multipart request; verify one synthetic photo+caption and PDF from fake provider, then isolated real Lab smoke with explicit approval.

**M3:** reuse the operator native attachment workflow and existing Connector durable outbox for outbound media; adapter already has isolated `SendFileByUpload` primitive in PR #8, not wired.

## Verification and stopping rules

Targeted tests only (repo `AGENTS.md`). Review the real native storage and policy code before modifying it. Test actual file size/hash, malformed multipart, same-ID changed content, missing media, and a synthetic upload whose storage write fails after beginning. Keep `InboxEvent` source identity and existing text receipt progression unchanged.

**Do not introduce** new persistence models, new media storage, cleanup workers, root/part grouping, native provider credential paths or extra UI merely to complete this increment. Any cross-event grouping requirement must be demonstrated, reviewed at Chatballs core level and approved separately.

No live/provider/production actions in this PR. Media runtime is **not yet implemented**.

## Review checklist

- [ ] Approve the narrower one-request multipart media capability as an initial profile alongside existing JSON `event.v1`.
- [ ] Confirm current 20 MiB native file limit and initial JPEG/PNG/PDF matrix, plus web-server/Django upload limits.
- [ ] Confirm a stable adapter `event.id` per provider root for this pilot.
- [ ] Confirm file-write error handling and storage cleanup evidence in M1 tests.
- [ ] Preserve full-v1 `media_ref` research as a **future option if demonstrated necessary**, not an implicit implementation mandate.

The architecture objective is native reuse. One Connector event becomes ordinary Chatballs messages and attachments without a shadow subsystem.
