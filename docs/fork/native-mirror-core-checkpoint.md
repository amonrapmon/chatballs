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

## Checkpoint D: Gateway publication claim (2026-10-12)

**Code committed, PostgreSQL tests still pending.**

### Durable decision

- Added `NativeMirrorPublication` per Gateway AI Message with its original
  conversation revision and status `QUEUED / CLAIMED / SUPPRESSED`.
- `native_mirror.0002_gateway_publication` creates the additive model;
  `tenancy.0046_native_mirror_publication_guards` adds owner, RLS, runtime
  grants and the tenant-aware message FK trigger.
- The AI result transaction now creates Message, existing Gateway outbox
  command **and** publication record together. Failure to queue the guard
  rolls back the AI result and outbound command. No extra transport layer.
- The Gateway event handler checks persisted publication under the Conversation
  lock before issuing HTTP. If current revision != queued revision, mark
  SUPPRESSED and return without HTTP. The outer worker marks the outbox event
  processed as usual. If still current, first record CLAIMED and commit;
  only then perform HTTP outside transaction.
- CLAIMED is the irrevocable **publication boundary**, not the generic
  `OutboxEvent.PROCESSING` worker lease. On network timeout, retry the
  exact same durable command ID even after a newer native reply. No claim
  of exactly-once network delivery.
- Operator and pre-existing legacy Gateway commands have no publication
  record and retain their previous dispatch behavior. Snapshot-based AI
  claims are created only for integration `native_mirror_mode=ENABLED`.
  A later mode toggle does not silently erase a previously queued claim.
- Checkpoint D does not change current `Message.delivery_status` mapping.
  A SUPPRESSED AI Message may therefore still display queued in the UI.
  **This must be resolved before enabling this flow for users** using a
  separately approved product status/presentation contract. Also, canonical
  AI messages already committed before suppression remain in Chatballs
  history; the guard prevents outbound HTTP, not earlier local visibility.

### Verification gate

- New `test_gateway_publication.py` and
  `test_gateway_publication_races.py`: pre-claim suppression, post-claim
  retries, failed network handoff, other commands unchanged, tenant
  isolation/foreign FK, cross-worker lock ordering and transaction rollback.
- New migrations require `--create-db` once on a disposable test database.
- Regression paths: `conversations/test_gateway_ai_delivery.py`,
  `conversations/test_ai_turn_concurrency.py`,
  `native_mirror/test_supersession*.py`,
  `native_mirror/test_persistence*.py` and the new publication tests.
- Do not merge or deploy until these targeted tests pass and the remaining
  UI/canonical-history status behavior is reviewed.

## Checkpoint E: suppressed message semantics (2026-10-12)

**Implemented, regression tests NOT yet executed.**

### Canonical semantics

- A Gateway AI reply with publication `SUPPRESSED` is **never sent**, and
  canonical Message gets `delivery_status=suppressed` within the same tenant
  transaction. Original Message, Gateway command ID and publication audit
  record stay immutable and inspectable in technical diagnostics/DB.
- Additive `conversations.0033_message_delivery_suppressed` expands only
  the enum choices. No new public UI element or banner is introduced.
- Verified provider callbacks for a suppressed command are rejected (409):
  they may not rewrite the terminal status or attach a provider message ID.
- Shared `native_mirror.visibility.visible_messages()` excludes suppressed
  AI replies from the ordinary operator history (including cursor windows),
  list preview/last message and pending-count calculations, full-text search,
  AI context history and public WEB history. A cancellation updates
  `Conversation.last_message_at` using the most recent visible message.
- A suppression commits a `conversation.changed` refresh notification.
  The message history delta `?after=<message_id>` includes `removedIds`
  for suppressed message IDs already known by the browser.
  `useConversationHistory` removes those messages from state without visual
  placeholders and continues displaying subsequent messages. The hook also
  loads the next tail when the current visible history is empty.
- The normal conversation UI remains exactly as designed. Diagnostics keep
  the record, with explicit suppressed status. Existing Gateway operator
  messages and all LEGACY messages still use the same endpoints as before.

### Limits

- Events and diagnostic traces of AI tool calls (including real external side
  effects) are **not** erased. Suppression only retracts an AI answer that
  never passed the durable dispatch boundary.
- Delta `removedIds` currently returns all suppressed IDs with id <= cursor
  for the conversation. This is correct for already loaded older windows but
  should be monitored for payload growth in very long-lived conversations.
- Checkpoint E does not authorize any TG/MAX/VK adapter or product rollout.

### Verification gate

- Backend: `native_mirror/test_suppressed_visibility.py`,
  `native_mirror/test_gateway_publication.py`,
  `native_mirror/test_gateway_publication_races.py`,
  `conversations/test_history_window.py`,
  `conversations/test_query_budget.py`,
  `conversations/test_gateway_ai_delivery.py`,
  `gateway_ingress/test_delivery_status_transitions.py`,
  plus `conversations/test_ai_turn.py`.
- Frontend: `apps/internal-ui/src/features/conversations/historyDelta.test.ts`
  and `npm --workspace @chatballs/internal-ui run typecheck`.
- New Message choices migration requires `--create-db` once on disposable
  PostgreSQL test data. No production or real gateway credentials.

## Checkpoint F: TG/MAX authenticated native Gateway adapter (2026-10-12)

**Implemented in GitHub branches; PostgreSQL and TS tests have NOT yet run.**

### Compatibility and mode semantics

- Reuses the existing authenticated `/gateway/integrations/<id>/operator-mirror/`
  endpoint. The old `intercom-gw.chatballs.operator-mirror.v1` schema, token,
  response shape and source_id checks remain in place.
- `LEGACY` (missing/invalid/default): preserves existing InboxEvent dedup,
  `Message(OPERATOR)`, automatic `control_mode=HUMAN` and prior ACK.
- `DISABLED`: after authentication/schema/source validation, returns 202
  without any user-conversation or durable Native Mirror changes.
- `SHADOW`: authenticated event is inspected with provider-event attestation
  and own-message ID correlation; emits privacy-safe diagnostic counters in
  service logs (hashed event ID, boolean flags), but **does not write**
  Message, InboxEvent, revision, receipt or AI-turn changes. Raw provider
  events remain durably stored by intercom-gw.
- `ENABLED`: accepts only provider-attested
  `origin.provider_event_type=outgoingMessageReceived` and a non-null
  timezone-aware provider timestamp. An old un-attested event fails closed
  with 409, never silently assuming a verified native origin.
- Trusted native origin is an *authenticated native-app provider event*
  carried by first-party intercom-gw. The canonical operator author is the
  explicitly configured `native_operator_user_id` bridge service account
  with active tenant membership, **not** proof of the personal identity of
  whoever used the native app. The account may be inactive for login.
- `ENABLED` delegates to the durable `accept_native_reply()` service:
  provider/message dedup, pending receipt replay, self-echo correlation,
  revision and AI supersession. It keeps `control_mode` and
  `expected_responder` unchanged.
- `RETRYABLE` and `UNMATCHED` are 202 only if the complete event has
  committed to the durable NativeMirrorReceipt for later replay. Conflicting
  IDs / membership failures are rejected.
- Endpoint auth/source checks happen before mode routing. No new public API,
  no schema migration and no production flags changed by this stage.

### Cross-repository contract

In `amonrapmon/intercom-gw` branch `feat/native-mirror-provenance`,
both TG and MAX destinations add optional

```json
"origin": { "provider_event_type": "outgoingMessageReceived" }
```

to the existing operator-mirror.v1 JSON payload, taken from the
authenticated GREEN-API normalizer `event.eventName` (not a new heuristic
based on missing outbound mapping). The destination filters already accept
only `outgoingMessageReceived`, not `outgoingAPIMessageReceived`. Legacy
Chatballs ignores this additive field.

### Safe rollout sequence (not performed)

1. Test both branches locally with fake transport; ensure LEGACY existing
   cases and new mode tests pass.
2. Deploy Gateway provenance support **before** switching Chatballs native
   mirror to ENABLED. Old clients stay LEGACY until explicitly configured.
3. Observe SHADOW diagnostics from TG and MAX synthetic/test conversations,
   verify event provenance, source mapping, bridge identity and no echo.
4. Only after approved integration smoke enable one test integration at a
   time. Production integration data, tokens and deploy are outside scope.

### Targeted verification

- Chatballs PostgreSQL: `gateway_ingress/test_operator_mirror.py`,
  `gateway_ingress/test_native_operator_adapter.py`,
  `gateway_ingress/test_ingress.py`,
  `native_mirror/test_persistence.py`,
  `native_mirror/test_supersession.py`,
  `conversations/test_gateway_ai_delivery.py`.
- Gateway Vitest: TG and MAX `src/destinations/chatballs-destination.test.ts`;
  their individual TypeScript checks or repository `check:tg`/`check:max`.
- No new migrations since previous checkpoint and no production actions.

## Checkpoint G: synthetic cross-repository contract smoke (2026-10-12)

**Harness committed but not yet executed.** See
`docs/fork/native-mirror-cross-repo-smoke.md`.

The `intercom-gw` feature branch produces synthetic TG/MAX JSON through
its actual webhook normalizer, provider routing and Chatballs destination.
Six opt-in PostgreSQL integration test methods in Chatballs process that
bundle through the actual DRF ingress, receipt, revision, AI-turn and
publication logic. No real provider call or inter-container socket yet.

## Checkpoint H: isolated TG/MAX network HTTP smoke (2026-10-12)

**Committed, awaiting execution on the owner's Docker test environment.**

- `compose.native-mirror-network-smoke.yaml` adds separate private TG and
  MAX Fastify service containers plus a Django LiveServer pytest runner to
  the existing disposable `cb-native-mirror-test` project. No extra host
  ports, no production networks or mounts, no real provider credentials.
- `intercom-gw/tools/native-mirror-network/server.mjs` uses the real
  Fastify callback routes, normalizers, provider event service,
  `ChatballsDestination` HTTP client and delivery-command endpoint;
  provider persistence is **test-only in memory** and no send to GREEN-API
  can occur. Separate test Dockerfile builds both gateway packages from
  source using maintained npm scripts.
- `native_mirror/smoke_network.py` runs live Django HTTP on a dynamically
  allocated container port; `network_smoke_support.py` contains strictly
  test-only HTTP fixtures. Fastify sidecars connect to the live Django
  server via `native-smoke-runner` service DNS and real HTTP.
- Tests exercise TG and MAX under `SHADOW`, `ENABLED`, webhook Bearer
  validation, Chatballs integration Bearer validation, synthetic HTTP 503
  plus retry, receipt dedup, supersession / resumed AI, source checks and
  both orders of the durable Gateway claim/native mirror boundary.
- **Not yet verified**: Docker image build, private DNS, Django LiveServer
  routing and the new HTTP test assertions. No production rollout.
- Execution commands and known limitations:
  `docs/fork/native-mirror-network-smoke.md`.

## Remaining

- Stage 2B: durable Gateway publication claim and pre-dispatch stale guard,
  with strict ordering and outbox retry behavior.
- Pending replay scheduler, bounded retry/dead-letter policy.
- Stage 3: opt-in TG/MAX Gateway adapter behind LEGACY / SHADOW / ENABLED.
- Stage 4: VK Bots Long Poll evidence, persisted send correlation,
  durable cursor ACK and echo-before-mapping tests.
