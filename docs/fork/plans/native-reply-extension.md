# Implementation plan: Native External Reply Extension

**Status:** draft for owner review; **scope of this delivery:** stage 0 research/docs update (2026-10-09).
**Repository:** `amonrapmon/chatballs`. **Baseline:** `feat/native-reply-extension` @ `330960b81ac78dc36e1b05fbfa2730b7888bb3bc` (upstream v1.17.2 + Gateway).
**Working branch:** `feat/native-reply-extension`. **Design authority:** `docs/fork/adr/0001-native-external-replies.md`.

## 0. Rules and work boundaries

- Read root `AGENTS.md`, upstream ADR-0002/0028 and this fork ADR before edits. No implementation before owner explicitly approves the design.
- No production/server changes, no runtime code, no DB schema changes at stage 0.
- New fork code must be in isolated module(s); core hooks minimal, explicit and unit tested. DRY/SRP, no god files, no implicit control-mode changes.
- Targeted tests only, `--reuse-db`; full suite only on explicit owner instruction.
- Separate commits for adapter, core hook, data migration, tests. Never combine incidental upstream refactoring.
- Preserve `operator-mirror.v1` contract and existing gateway auth until a new contract is explicitly approved.

- Do not emulate WEB sessions for external transports, duplicate VK polling cursor, or replace durable Green-API TG/MAX with WEB. Preserve upstream WEB/VK behavior in `DISABLED` and current TG/MAX mirror in default `LEGACY`.

## 1. Verified baseline / current functional flow

| Surface | Current behavior | Engineering consequence |
| --- | --- | --- |
| `gateway_ingress/operator_mirror.py` | TG/MAX mirror event dedup via `InboxEvent`, creates `Message(OPERATOR)`, sets `HUMAN`; missing/ambiguous conversation is only logged | Delegate to canonical service; define non-lossy outcome policy; keep LEGACY |
| `gateway_ingress/payloads.py`, `services.py` | `operator-mirror.v1`, required metadata; tenant-scoped auth | Do not break client-facing schema, source checks or membership |
| `conversations/transports/vk.py` | `poll_updates -> _messages -> _normalize` only `message_new`; `from_id < 0` ignored | Need a separate event type / adapter, not to mislabel as client inbound |
| `conversations/transports/vk_send.py` | `messages.send` creates random_id, returns bool, no persisted provider message ID | Must add reliable echo correlation for all Chatballs sends |
| `conversations/poller.py` | Loops normalized inbound, logs ingest errors, advances marker | Need durable staging and no premature VK ack |
| `conversations/ingest.py` | Stores customer message and requests async AI-turn | Native external outgoing must not call `ingest_inbound` |
| `conversations/ai_turn.py` | PENDING->RUNNING; result persisted in short transaction; send afterwards | Need pre-persistence validation and publication race policy |
| `conversations/ai_turn_result.py` | `store_answer` and `store_failure` write messages, queue/handoff, notify | Stale path must not emit these side effects |
| `conversations/models.py` | `AiTurnState` has no SUPERSEDED; `external_id` not unique | Avoid assuming existing state/ID gives complete idempotency |
| `.skaro/adr/0002*`, `0028*` | HUMAN takeover explicit; event worker independent of poller | Preserve upstream contract, do not auto-switch control_mode |

| Historical `intercom-gw@b3fdf9f/vk-gateway` | Callback API `message_reply` normalized as outgoing; native reply mirrored to Chatwoot using provider ID mappings | Proven correlation concept and tests; adapt, do not copy Chatwoot dependencies or assume race-free delivery |
| `intercom-gw@f76f218` | Chatwoot legacy / old VK gateway removed | Do not resurrect old callback consumer |
| `webchat/{services,sessions,message_history}.py` | WEB session and UUID inbound -> `ingest_inbound`; browser polls DB history; send noop | Not a generic server-to-server Telegram/MAX transport |
| `conversations/transports/{telegram,max}.py` | Native Bot API polling/sending/media | Functional upstream paths but not our Green-API transport |
| `intercom-gw@main` shared DB + delivery worker | Durable commands/attempts, provider events, status projections, source-scoped worker claim | Keep TG/MAX delivery architecture rather than reimplement via WEB |

## 2. Stage 0.5: proof and design decisions (NO production mutation)

Before implementing architecture, close these questions using small read-only probes or isolated tests:

1. **VK event:** use historical Callback fixtures for comparison, then obtain sanitized **Bots Long Poll** `message_reply` and `messages.send` responses (AI, manual Chatballs, native community operator). Check `id`, `peer_id`, `conversation_message_id`, `out`, `random_id` and optional `admin_author_id`; do not assume Callback == Long Poll or attribute unmapped admin ID to employee. Never log tokens or personal chat content.
2. **Correlation:** test the historical pattern `messages.send provider messageId -> outbound mapping -> suppress matching message_reply` before designing replacements. Specifically stress echo-before-mapping, missing send response, redelivery, restart and all VK send paths (AI/manual/call/file). If necessary design a durable outbound-intent registry or outbox; do not infer self-echo from sender fields alone.
3. **Poller durability:** decide whether `poll_updates` returns a `PollBatch(inbound, native_events, next_marker)` or an equivalent typed envelope. Store interesting events durably before advancing the cursor. Test failure/restart/redelivery. Reject an in-memory side-channel and a second VK consumer of the same cursor.
4. **Concurrency:** enumerate all result paths in `ai_turn.py`: `_begin`, `_apply_transcript`, `plan_chat` failure, `run_turn_chat`, `record_turn`, `store_answer`, `store_failure`, `_deliver`. Build a deterministic barrier test for the save/send boundary.
5. **Tenant DB:** choose separate `native_mirror` state and processed-event tables, uniqueness, foreign keys, required tenant RLS/grants, migrations. Confirm new schema can be deployed and rolled out with LEGACY as default.
6. **Classification:** decide when unknown community sender counts as authoritative. No confirmed actor -> no invented named operator. Prefer conservative behavior; enable supersede only when authorized policy is explicit.
7. **Send semantics:** choose whether an AI response is claimed for send through the existing outbox (preferred candidate) or weaker pre-send best effort. Document linearization point, in-flight send race and network failure outcomes.

8. **Compatibility baseline:** document hooks with upstream symbol, mode/fallback, targeted tests and merge risks. Include WEB widget, native VK (feature DISABLED), TG/MAX (LEGACY) regression cases. No WEB-session emulation, second VK receiver or replicated AI core.

**Gate S0:** owner reviews ADR revision + selected architecture/guarantees. If no reliable VK correlation/ack or no sound AI publication model, stop and present tradeoffs instead of writing fragile patch.

## 3. Stage 1: canonical native_mirror domain, no channel adapters yet

Suggested additive files (final layout may change after Gate S0):

```text
apps/backend/chatballs/native_mirror/
  __init__.py
  contracts.py            # validated event + outcome
  classification.py       # self-echo / authorized / unknown
  policy.py               # DISABLED / LEGACY / SHADOW / ENABLED
  service.py              # accept(event, tenant context)
  state.py                # durable per-conversation revision and dedup state
  supersession.py         # stale-turn policy / atomic mutation
  vk_adapter.py           # convert VK message_reply only
  tests/
```

Define `accept(event, context) -> {stored|duplicate|self_echo|retryable|unmatched|ignored}` or typed equivalent. Idempotency must not be based on message text. Use DB constraints, tenant context, connection verification, and one unambiguous open conversation. Atomic persistence of message + relevant state + event outcome; no outbound send or AI scheduling from acceptance. Update inbox ordering and other required metadata consistently with upstream.

Keep RLS and installation DB-roles intact. Add migration only after schema is agreed; don't modify existing historical migrations.

Unified `native_mirror` is a domain feature, not a second transport layer. WEB stays a browser widget, built-in VK retains Bots Long Poll and TG/MAX continue through `intercom-gw` with current delivery commands, attempts, retries and statuses.

**Gate S1:** targeted tests for dedup, source mismatch, wrong tenant, unmatched conversation, retry, no outbound, AI/HUMAN/PAUSED preservation.

## 4. Stage 2: supersession without AI lifecycle fork

Design candidate: durable per-conversation `mirror_revision`, plus marking older PENDING work stale; RUNNING work captures revision before model/tool request and must re-check it **under lock** before any result persistence.

The stage must prevent all **post-supersede state changes**, not just the text send:

- prevent `record_turn` from saving a stale result;
- prevent `store_answer`, handoff and operator notifications from stale results;
- prevent `store_failure` and AI-unavailable fallback from stale results;
- prevent stale `tool_call_events` and unwanted transcript/handoff side effects where possible;
- stop `conversation_is_thinking` from showing a dead turn forever;
- keep a later client message eligible for a fresh AI-turn.

Handle old PENDING event by explicit superseded/terminal marker or snapshot captured at scheduling. A revision first read at `_begin` is **insufficient** for a turn enqueued before the mirror event. Decide whether `DONE` is acceptable as internal termination or whether a new distinct state is worth the added migration/upstream diff.

Model the save -> dispatch race. If a send has already been durably claimed or entered a provider request, a later external reply might not prevent delivery. Never promise absolute exclusion of simultaneous responses without an atomic publication protocol. Keep network activity outside DB transaction. If using delivery outbox, make dispatch idempotent and define retry/status behavior and dedup.

**Gate S2:** barrier/race tests for `PENDING`, `RUNNING`, after-LLM-before-store, before-claim, after-claim/in-flight-send, tool-call and failure branches. All without real LLM provider.

## 5. Stage 3: existing TG/MAX Gateway mirror migration

- Preserve endpoint `/api/v1/gateway/integrations/{id}/operator-mirror/`, current auth, `source_id`, contract `intercom-gw.chatballs.operator-mirror.v1`.
- Gateway adapter resolves trusted source/native author and delegates to `native_mirror.accept` in ENABLED, retains existing semantics in LEGACY.
- In SHADOW, leave existing behavior intact and emit decision-only telemetry without duplicate Message.
- In DISABLED, no mirror side effects, with explicit documented acknowledgment/outcome.
- Don't change `delivery_status`, outbound commands, general customer ingress, or Green-API transport unless a failing test shows necessity.
- Keep `intercom-gw` untouched until contract gap is demonstrated. If change required, separate PR/commit and compatibility matrix.

- Do not backport historical Chatwoot VK persistence or switch TG/MAX to WEB; the old mapping implementation is reference material for the current Chatballs VK adapter.

**Gate S3:** authenticated/unauthenticated, duplicate delivery, missing/ambiguous dialog, membership, AI mode preservation, reverse toggle, TG and MAX samples.

## 6. Stage 4: native VK mirror in two substeps

### 4A. Diagnostic-only SHADOW

- Capture `message_reply` as typed event, without sending it to customer inbound processor.

- Source only from the existing Chatballs Bots Long Poll; the old gateway used VK Callback API. Compare fixtures but do not reuse its HTTP receiver or start a second cursor.
- Collect only safe metadata: event type, numeric IDs hashed/redacted, out flag, optional `admin_author_id` presence (redact actual ID), correlation result, event age; never secrets/message text. Personal attribution requires explicit tenant/membership mapping.
- Verify whether own responses from Chatballs include reliable provider ID/random_id correlation; cover calls, files and manual replies as well as AI text.
- Ensure VK parser transport remains compatible if events are not enabled in community settings.
- Verify acknowledged vs retried batches and restart; don't advance cursor beyond an unstaged mandatory event.

### 4B. ENABLED for a test connection

- Route only confirmed external personal text replies into canonical mirror.
- `SELF_ECHO` produces no second Message. `EXTERNAL_UNCLASSIFIED` follows conservative policy with no implicit AI interruption.

- Confirmed native reply is distinguished from `SELF_ECHO` by persisted provider-ID correlation, not simply missing outbound mapping during echo-before-mapping races. Unknown/absent VK admin identity stays unclassified.
- Unknown VK user attribution is represented clearly and never elevated to a confirmed staff identity.
- Preserve all `message_new` inbound behavior and VK cursor/backoff semantics.

**Gate S4:** natively sent VK text shows exactly once, Chatballs-originated text/call/file never duplicates, client next message gets AI, bad event retries, old/new toggles work.

## 7. Stage 5: deployment and verification

**No deployment during stage 0.** After owner approval of implementation:

1. Isolated test DB + new additive migrations, `makemigrations --check`, `showmigrations --plan` with migration role (not runtime DB role), migration rehearsal. Backup test data before any schema changes.
2. Targeted pytest for `gateway_ingress`, `native_mirror`, `conversations/test_ai_turn.py`, `conversations/test_vk_transport.py`, relevant poller/worker tests. Use `--reuse-db`; `--create-db` only when schema truly changed.
3. Backend lint/type smoke applicable to changed files; UI only if UI was changed (stage v1 aims to avoid UI).
4. Deploy with LEGACY default to test installation, verify DB/RLS, worker-events/poller logs and existing TG/MAX/VK inbound/outbound.
5. Enable SHADOW for representative VK, inspect correlation metrics, move one test connection to ENABLED, run live concurrent scenarios, then TG/MAX ENABLED.
6. Rollback switch `ENABLED -> LEGACY` or `DISABLED`; no DB restore to switch flag. Avoid changing active production credentials or installation config without explicit approval.

## 8. Acceptance matrix

| Case | Expected behavior |
| --- | --- |
| External trusted reply when AI thinking | One canonical Message, earlier AI-turn stale, `control_mode` remains AI |
| Next customer message after external reply | Normal new AI-turn |
| Explicit HUMAN / PAUSED | Remain HUMAN / PAUSED; no unintended AI resume |
| VK Chatballs outbound echo | No duplicate Message, no supersede |
| Same external event twice | Exactly one canonical Message |
| Same text but different provider message IDs | Two separate events, not falsely deduplicated |
| Different organizations, equal external_chat_id | No cross-tenant mapping |
| Unmatched or ambiguous dialogue | Recorded outcome; no wrong-conversation message |
| VK staging failed before marker commit | Event redelivered, no silent loss |
| AI provider error after supersede | No AI fallback, handoff or user-facing stale send |
| External tool already executed | Not claimed reversible; audit outcome |
| Toggle ENABLED -> LEGACY/DISABLED | Subsequent events follow chosen mode, existing history preserved |

| VK Callback vs Bots Long Poll | Historical fixtures are reference only; current adapter accepts proven Bots Long Poll fields |
| Optional `admin_author_id` | Can inform author mapping only when real payload and tenant mapping verify it |
| WEB feature-disabled regression | Web session, UUID-based message ingestion and polling of history unchanged |
| VK DISABLED | VK `message_new`, polling/backoff, own outbound and AI lifecycle match upstream |
| TG/MAX LEGACY | Existing mirror+HUMAN, delivery/retry/status behavior unchanged; WEB not used |

## 9. Fork compatibility budget

For every integration hook document `path`, `upstream entry point`, small diff, fallback policy, tests, and expected upstream refactor risks. Proposed touch points:

| Candidate upstream file | Purpose | Risk | Status |
| --- | --- | --- | --- |
| `conversations/transports/vk.py` | Typed external reply extraction | medium | design only |
| `conversations/poller.py` or transport facade | Durable stage before cursor commit | high | design only |
| `conversations/ai_turn.py` | Pre-persist stale guard + send claim | high | design only |
| `conversations/ai_turn_result.py` | Only if guard cannot cover all paths upstream | high | avoid if possible |
| `conversations/transports/vk_send.py` | Durable own-outbound correlation | medium | design only |
| `gateway_ingress/operator_mirror.py` | Delegate TG/MAX to domain | low (fork-owned) | design only |

**Budget is a goal, not permission to weaken correctness:** additive files unlimited within project engineering rules; aim for a handful of small integration changes, but if a safe send guarantee requires more, stop, revise ADR, get owner approval. No monkey patches and no copying whole upstream modules.

### Mandatory fork compatibility checklist

For each core integration hook record **before implementation** and revalidate
**after every upstream merge, including conflict-free merges**:

| Field | Required content |
| --- | --- |
| Path / upstream symbol | Exact path and function receiving the hook |
| Purpose / patch budget | Why the integration cannot live wholly in `native_mirror/*` |
| Mode / fallback | LEGACY, DISABLED, SHADOW, ENABLED behavior at the hook |
| Upstream baseline | Exact unchanged behavior when extension is disabled |
| Targeted regression | Mode switching, dedup, cursor/retry, transport and AI race tests |
| Merge risk / reviewed version | Upstream refactor risks, reviewed release/commit and test results |

Release gate includes WEB non-regression, VK DISABLED parity, TG/MAX LEGACY
parity and inspection of all affected core hooks. Clean Docker builds or a
conflict-free merge alone do not prove compatibility.

## 10. End of stage 0 checklist

- [x] Read actual Gateway mirror and VK polling/sending paths.
- [x] Read AI turn and result persistence/dispatch paths.
- [x] Read upstream ADR-0002, ADR-0028 and VK integration spec.
- [x] Identify message persistence, cursor ack and race hazards.
- [x] Draft fork-scoped ADR and an implementation plan.

- [x] Read historical VK Callback normalizer, mirror/mapping and tests in `intercom-gw@b3fdf9f`.
- [x] Review WEB widget and native TG/MAX vs durable Green-API Gateway; reject WEB as TG/MAX replacement.
- [x] Specify fork compatibility checklist and extension-disabled behavior.
- [ ] Validate current Bots Long Poll payload against historical Callback fixtures and possible `admin_author_id`.
- [ ] Obtain masked VK event/response samples from test community.
- [ ] Choose publication claim protocol and event staging design.
- [ ] Owner accepts final ADR and authorizes runtime implementation.

## References for 2026-10-09 research

- Historical VK Callback normalizer: https://github.com/amonrapmon/intercom-gw/blob/b3fdf9f90be9269edda8dec50d37604d4e857c37/vk-gateway/src/transports/vk/vk-normalizer.ts
- Historical native reply mirror: https://github.com/amonrapmon/intercom-gw/blob/b3fdf9f90be9269edda8dec50d37604d4e857c37/vk-gateway/src/services/native-reply-mirror-service.ts
- Historical VK outbound mapping: https://github.com/amonrapmon/intercom-gw/blob/b3fdf9f90be9269edda8dec50d37604d4e857c37/vk-gateway/src/services/outbound-dispatch-service.ts
- Legacy removal: https://github.com/amonrapmon/intercom-gw/commit/f76f218bd306826ae37f21617f5d32691aa6e6f5
- Current Chatballs `@330960b`: `webchat/{services,sessions,message_history}.py`, `conversations/transports/{__init__,telegram,max,vk,vk_send}.py`, `gateway_ingress/services.py`.
- Current `intercom-gw@main`: `db/src/schema.ts`, `tg-gateway/src/services/delivery-command-worker.ts`.

**Stop here.** This plan does not authorize modifying application files, creating DB migrations, enabling network listeners or deploying to a server.
