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
  provider message ID + chat ID uniqueness, original provider/source, payload fingerprint, processing
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
  The adapter/worker must respect this result. `replay_pending_receipt()`
  reconstructs verified events from stored receipts after restart without
  a provider redelivery. **Automatic pending scheduling is not implemented yet.**
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

## Checkpoint C: AI-turn supersession (2026-10-12)

**Implementation committed, targeted regression tests NOT yet executed.**

- Ingest now locks Conversation and captures mirror revision while creating
  the incoming customer Message. `request_ai_turn` reacquires that lock,
  compares the captured revision, and commits PENDING + the Outbox payload
  `mirrorRevision` atomically. This specifically closes the gap between
  customer Message persistence and queueing.
- AI begin, transcription persistence and all guarded completion paths check
  the queued revision under the Conversation lock. A mismatch terminalizes
  PENDING/RUNNING as DONE without writing an AI reply, fallback or handoff.
- Successful authorized mirror acceptance increments revision AND clears
  already queued/running AI-turn states in the same tenant transaction that
  stores the operator's native reply. Duplicate, unknown and echo events
  do not increment revision or supersede active work.
- Newly arriving customer messages capture the new revision and may start
  their own AI turns. `OBSERVE` keeps control_mode AI.
- Legacy queue payloads without `mirrorRevision` keep existing eligibility
  rules; the mirror's explicit terminalization still rejects pre-existing
  PENDING/RUNNING turns when a new native reply is committed.
- No new migrations for Checkpoint C. Stage 1 schema/permissions remain.
- `test_supersession.py` and `test_supersession_races.py` cover stale
  PENDING/RUNNING, planning failure, transcription, post-mirror fresh turns,
  duplicate event, concurrent finalization, full model result, rollback,
  and inbound-persist-before-queue timing.

### Deliberate remaining publication limitation

- **Atomic result persistence is not equivalent to revocable delivery.**
  Once Gateway AI Message and delivery Outbox are durably committed, a native
  reply cannot automatically cancel a claimed or in-flight network send.
  Non-Gateway synchronous sends still occur after commit without a durable
  claim. This requires a separate Stage 2 publication-claim/dispatch policy,
  and race tests for before-claim and after-claim cases.
- Tool side effects already executed externally are likewise not reversible.
  Future tooling policy must deal with those separately.

## Verification gate for Checkpoint C

Run only targeted tests against the owner's disposable PostgreSQL:
`native_mirror/test_supersession.py`,
`native_mirror/test_supersession_races.py`,
`native_mirror/test_persistence.py`,
`conversations/test_ai_turn.py`,
`conversations/test_ai_turn_concurrency.py`.
Use `--reuse-db`; no schema changed for Checkpoint C.
Check `makemigrations --check --dry-run` and backend lint. Do not deploy
the experimental branch to production. No adapter is connected yet.

## Remaining

- Stage 2B: durable Gateway publication claim and pre-dispatch stale guard,
  with strict ordering and outbox retry behavior.
- Pending replay scheduler, bounded retry/dead-letter policy.
- Stage 3: opt-in TG/MAX Gateway adapter behind LEGACY / SHADOW / ENABLED.
- Stage 4: VK Bots Long Poll evidence, persisted send correlation,
  durable cursor ACK and echo-before-mapping tests.
