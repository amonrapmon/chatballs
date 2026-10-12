# Native Mirror Core: implementation checkpoints

Branch: `feat/native-mirror-core` (based on `feat/native-reply-extension@84cb117`).
This branch is experimental. Nothing is wired into the production TG/MAX/VK transports.

## Checkpoint A: pure contracts (2026-10-12)

- Validated normalized text event and typed outcome.
- Conservative author classification and per-integration modes, default LEGACY.
- 12 pure tests **passed** on the owner's disposable Docker setup.
- First commit: `8229e6b`.

## Checkpoint B: PostgreSQL persistence (2026-10-12)

### Schema

- `native_mirror_nativemirrorreceipt`: integration-scoped `event_id`,
  provider message ID + chat ID uniqueness, payload fingerprint, processing
  status, retry count/reason and optional canonical Message. On missing or
  ambiguous conversation: PENDING with text retained for reprocessing.
  On success: creates canonical Message and clears staging text.
- `native_mirror_nativemirrorconversationstate`: unique per-conversation
  positive revision, advanced once per newly stored authorized external reply.
  **AI does not yet check this revision**; that belongs to Stage 2.
- `native_mirror.0001_initial` creates only the tables.
- `tenancy.0045_native_mirror_guards` assigns schema ownership, RLS
  and app grants; tenant FK triggers guard integration, conversation, message;
  membership trigger guards the receipt's author user.
- No existing Message/Conversation schema changes and no API changes.

### Transaction and ACK rules

- `accept_native_reply()` requires an authenticated, normalized event and
  trusted adapter-classified origin; it revalidates tenant, integration,
  source and authorized staff membership before writing anything.
- ENABLED only. Default/malformed configuration stays LEGACY and this
  new service returns IGNORED. No adapters call it yet.
- Lock order: `Conversation -> NativeMirrorConversationState ->
  NativeMirrorReceipt -> Message`, in one `tenant_atomic()`.
  No network/LLM call under lock. A missing conversation has no
  conversation/state lock and only creates a pending receipt.
- Identical event ID or provider message ID is not written twice.
  Reused identity with conflicting content raises `NativeMirrorConflict`
  rather than being silently acknowledged.
- No dialog: PENDING/retryable. More than one matching open dialog:
  PENDING/unmatched/retryable, reason persisted. No ack-as-success.
  The adapter/worker must respect this result and arrange redelivery or
  later pending replay. **Automatic pending replay is not implemented yet.**
- Own Gateway outbound with a confirmed stored `gateway_command_id` and
  provider ID is SELF_ECHO; unknown sender remains UNCLASSIFIED, never a
  fabricated operator. Full VK correlation/echo-before-mapping is still
  Stage 4 and not claimed solved by this code.
- After a validated native operator reply, canonical Message + receipt +
  conversation revision commit atomically. `control_mode`,
  `expected_responder`, ownership and AI scheduling are unchanged.
- Canonical Message is protected from hard deletion while referenced
  by a STORED receipt to avoid losing the receipt's integrity; normal
  conversation archive behavior is unchanged.

### Verification state

- New PostgreSQL tests: `native_mirror/test_persistence.py` and
  `native_mirror/test_persistence_database.py`.
- **Not yet executed**. A new migration requires a clean/disposable test
  database (one-time `pytest --create-db`), then `--reuse-db`.
- Check `makemigrations --check --dry-run`, migration plan, and targeted
  persistence/concurrency/RLS tests before any merge or deployment.
- Existing Gateway mirror with HUMAN takeover, AI delivery, VK/WEB and
  intercom-gw are unchanged.

## Remaining after persistence verification

- Stage 2: revision snapshot at AI scheduling/begin + guarded supersession
  at commit/publication, including PENDING and RUNNING races.
- Staged pending replay worker and bounded retry/dead-letter policy.
- Stage 3: opt-in TG/MAX Gateway adapter behind LEGACY / SHADOW / ENABLED.
- Stage 4: real VK Bots Long Poll evidence, persisted send correlation,
  durable cursor ACK and echo-before-mapping tests.
