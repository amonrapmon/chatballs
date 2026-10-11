# Task: AI-turn concurrent finalization guard

**Status:** implementation candidate on `fix/ai-turn-concurrent-finalization`; targeted PostgreSQL tests and code review pending.  
**Date:** 2026-10-10.  
**Repository / branch:** `amonrapmon/chatballs` / `feat/native-reply-extension`.  
**Original baseline:** `d52d308` (`fix(gateway): deliver AI replies through durable outbox`). **Implementation base:** `2da251d` (upstream `v1.17.3` merged with Gateway).  
**Related:** [Native Reply Extension plan](native-reply-extension.md), especially Stage 2, and [Native external replies ADR](../adr/0001-native-external-replies.md).

## 1. Why this task exists

Gateway AI Outbound v1 is implemented and its targeted PostgreSQL checks passed on 2026-10-10: **27 passed, 3 nonblocking warnings** in 43.52s (Gateway AI, Gateway operator reply, Gateway event delivery, AI turn).

That verifies the normal path, not real concurrent execution. In `conversations/ai_turn.py`, `_begin()` accepts both `PENDING` and `RUNNING`, because an abandoned RUNNING turn may be retried after an outbox processing lease expires. Two executions can therefore hold the same inbound message and compute an answer. Current `record_turn()`, `tool_call_events.record_tool_calls()`, `store_answer()` and `store_failure()` do not atomically re-read and guard the turn before mutating the conversation. Each execution might persist its own AI message and (for Gateway) its own durable outbound command.

A second race exists when a conversation moves away from AI while the model is responding: a stale result can currently persist after that control change, triggering handoff, notifications or an outbound command.

**Goal:** only one eligible result for an inbound AI-turn may be committed; stale work must not publish a message, change ownership/queue state, enqueue Gateway delivery, or trigger notifications.

This is an **AI-turn correctness task**, independent of enabling native operator mirror. Do not implement `native_mirror`, VK adapters or new operator-mirror policies here.

## 2. Required invariants

1. For a specific inbound `Message.id`, at most one terminal AI-turn finalization wins. Concurrent/retried attempts cannot create a second AI reply, fallback, system event, handoff, notification or Gateway delivery command.
2. Freshness and the decision to finalize are checked **inside the same tenant-scoped PostgreSQL transaction** as the resulting mutations, under appropriate row locks. Checking a previously loaded Python model instance is not sufficient.
3. Validate at least the persisted inbound turn state (`RUNNING`), actual conversation control mode (`AI`), lifecycle, and active agent before accepting the result. Specify how cancellation is terminalized and ensure it does not leave `conversation_is_thinking()` true forever.
4. Lock ordering is deterministic across relevant paths. Audit `Conversation`, inbound `Message` and Gateway reply/command locks for deadlocks, and keep the lock scope short. Never hold locks while awaiting LLM, transcription, embeddings or provider network calls.
5. The validation/commit gate precedes **all** result-related DB effects: `record_turn()`, tool-call history/events, AI Message creation, `enter_queue()`, system events, notifications, `_finish()`, Gateway command/outbox. If the turn loses, none of these effects occur.
6. Existing `RUNNING` recovery after an expired outbox processing lease remains possible. Simply changing `_begin()` to accept only `PENDING` is **not** a valid fix. The winner is decided during atomic finalization, not by trusting a long-running in-memory worker.
7. Success, provider failure/fallback, handoff (with and without text), deadline-expired, missing-transcript, plan failure and transcription paths follow one consistent state/freshness policy. The result of a rejected/stale attempt must never be sent by `_deliver()`.
8. Gateway keeps `Message(author_type=AI)` plus one `gateway.delivery_command.requested.v1` outbox event in the same transaction and retains the existing `intercom-gw.delivery-command.v1` payload. The existing operator reply flow must remain unchanged.
9. No change to WEB, native VK or upstream Telegram/MAX delivery behavior beyond preventing stale/duplicate AI finalization. Preserve their existing transport contracts. Do not promise exactly-once **network delivery** for transports that send synchronously outside the DB transaction.
10. Respect tenant RLS and the separate platform/event worker role. No production data migration or rollout in this task.

## 3. Implementation boundaries and design requirements

### Audit before editing

Inspect these actual call sites and any indirect writes:

- `apps/backend/chatballs/conversations/ai_turn.py`: `_begin`, `_apply_transcript`, `run_requested_turn`, `_deliver`.
- `apps/backend/chatballs/conversations/ai_turn_result.py`: `store_answer`, `store_failure`, `store_voice_without_transcript`, `_finish`.
- `apps/backend/chatballs/ai/turn.py`: `plan_chat`, `record_turn`, and effects of tool execution.
- `apps/backend/chatballs/conversations/tool_call_events.py`.
- `apps/backend/chatballs/conversations/gateway_delivery.py`: `enqueue_gateway_delivery`, operator reply lock ordering.
- `apps/backend/chatballs/events/services.py`: claim/release of outbox processing leases and aggregate ordering.
- Explicit HUMAN/PAUSED handoff and control-mode write sites.

### Proposed shape (design candidate, not mandatory API)

Use a small, dedicated transactional finalization helper/service, rather than spreading weak `if state == RUNNING` checks across multiple callers:

1. Do expensive planning/model work outside the finalization transaction as today.
2. Begin `tenant_atomic(context)`. Acquire row locks in a **documented canonical order**, preferably conversation first and inbound message second, compatible with existing operator paths.
3. Re-read fresh persisted state and decide `accepted` or `stale`. The in-memory `Turn` is only a computation snapshot.
4. If stale, leave no result side effects. Terminalize the inbound turn only according to an explicit, race-safe cancellation policy.
5. If accepted, perform result recording and all message/queue/outbox/notification state changes **under the same transaction and locks**; finish the inbound turn once.
6. Return an explicit outcome to `run_requested_turn`. Call `_deliver` only for an accepted result after commit, never for discarded work.
7. Ensure duplicate attempts started from `RUNNING` cannot both pass the gate: second execution rechecks after the first commits and sees terminal state.

If existing states are sufficient, prefer **no migration**. If an execution token, lease or new terminal state is truly necessary, first document the failure case, schema/RLS impact and migration plan; do not invent state merely to fix one race. An in-memory mutex is insufficient for multiple worker processes.

### Important limitations and ordering

- Gateway: the accepted result plus durable outbox is the publication boundary. The later delivery worker and `intercom-gw` keep their existing retry/idempotency semantics. Do not cancel already claimed provider commands here.
- Other transports: `_deliver()` occurs after DB commit; protect against stale duplicate invocation, but be explicit that a crash after commit and before synchronous send can still lose a delivery. Do not add a new all-transport outbox as part of this task.
- Native Mirror Stage 2 will later introduce a per-conversation revision/supersession policy. Make the finalization gate extensible to a revision check, **without** adding mirror state or claiming current control-mode checks solve future observe-only native replies.
- External tool effects that have already occurred cannot be rolled back; document this boundary. Do not execute a tool or record its history merely because a stale turn finished computing if avoidable.
- No network access or provider calls while holding DB row locks; keep compatibility with existing tenant context and RLS.

## 4. Targeted PostgreSQL acceptance tests

Write deterministic concurrent tests with separate DB connections / threads or processes, transaction-capable test fixtures, explicit synchronization barriers and bounded timeouts. Avoid sleep-based race tests. Include tests of both accepted and rejected outcomes.

| Case | Expected result |
| --- | --- |
| Two workers finalize the same `RUNNING` inbound message | Exactly one terminal winner, one AI Message, one accepted result/history and no duplicate side effects |
| Gateway duplicate completion/replayed event | Exactly one `gateway_command_id`, one delivery-requested OutboxEvent, one AI Message |
| Worker resumes `RUNNING` after outbox lease expiration | Recovery remains possible; if original worker also returns, only one result commits |
| Conversation changes AI -> HUMAN or PAUSED after model work, before finalization | No stale AI Message, fallback, queue takeover, notification or Gateway outbox |
| Agent disabled or conversation closed while model computes | Stale result rejected with defined terminal state; no outbound |
| Provider failure and fallback races with a successful/other result | Only winning outcome is persisted; no duplicate AI-unavailable notification |
| Handoff token, nonempty and empty visible text | Handoff side effects occur once; no blank outbound command |
| Deadline exceeded before/while processing; plan-chat error | One legal terminal outcome; retries do not duplicate fallback or handoff |
| Transcription fails / cannot be produced while control changes | No stale queue/notification effects; no permanently RUNNING orphan |
| Failure while creating Gateway OutboxEvent after winner decision | Entire finalization rolls back; retry may safely succeed |
| Non-Gateway WEB, VK, TG/MAX baseline | No extra sends, no regression in normal state transitions or transport calls |
| Different organizations and equal-looking external IDs | No cross-tenant writes or locking mistakes |

Review any `TestCase`/nested atomic behavior: for genuine contention use `TransactionTestCase` or `pytest.mark.django_db(transaction=True)` as appropriate, rather than a simulated `select_for_update` inside one connection.

Suggested regression files:

- New focused `conversations/test_ai_turn_concurrency.py` (split into smaller modules if needed).
- Existing `conversations/test_ai_turn.py`.
- Existing `conversations/test_gateway_ai_delivery.py`.
- Existing `conversations/test_gateway_operator_reply.py`.
- Existing `conversations/test_gateway_event_delivery.py`.
- Only directly affected event/worker tests when code changes demand them.

**Run targeted tests only**, with `pytest -q --reuse-db` in the disposable PostgreSQL/Docker environment. No full suite unless the owner explicitly requests it.

## Implementation checkpoint (2026-10-12)

- Branch: `fix/ai-turn-concurrent-finalization`. The working feature branch and server are unchanged.
- New `conversations/ai_turn_guard.py`: conversation-first, message-second row locks and a fresh eligibility check for the persisted turn, lifecycle, control mode and agent.
- New `conversations/ai_turn_completion.py`: success/planning-failure result effects and the Gateway outbox only after an accepted finalization, all in one tenant transaction. Rejected work skips `_deliver`.
- `ai_turn.py`: protects `_begin`, late voice transcription, success and provider/planning failures; RUNNING recovery is preserved.
- `test_ai_turn_concurrency.py`: real two-connection PostgreSQL race cases, takeover, duplicate/failure, tenant isolation, outbox rollback and retry.
- **Verification pending:** this checkpoint is a committed source/test candidate, not a passing test report. Run the targeted suite on disposable PostgreSQL before considering a merge.
- **Known boundary:** completed-turn diagnostics are captured at the winner's finalization rather than during in-flight model execution, to avoid a stale worker overwriting the winning trace. That means a model-process crash before finalization cannot leave an in-progress snapshot. Non-Gateway network send and external tool execution are still outside transactional publication guarantees.

## 5. Definition of Done

- [ ] Document the concrete double-finalization and HUMAN/PAUSED race windows and the chosen linearization point.
- [ ] Implement one central atomic guard with deterministic lock ordering and a distinct accepted/stale outcome.
- [ ] Preserve abandoned RUNNING recovery, tenant isolation and Gateway's durable delivery transaction.
- [ ] Protect success, failure, handoff, deadline and voice/transcription branches; no stale notifications/tool-call history or send.
- [ ] Add deterministic two-connection PostgreSQL race tests and cover normal transport regressions.
- [ ] Pass relevant existing Gateway/AI tests and new targeted tests on disposable PostgreSQL (`--reuse-db`).
- [ ] `git diff --check`, syntax/lint for touched files and review against `AGENTS.md` (DRY, SRP, NO GOD FILES).
- [ ] Commit implementation separately from this planning document; no upstream/main merge, production rollout or server restart without owner authorization.
- [ ] Record remaining limitation: non-Gateway synchronous send is not guaranteed exactly-once; future Native Mirror revision supersession is separate.

**Out of scope:** native reply ingestion, VK correlation, TG/MAX mirror policy, production deployment, rewriting event worker scheduling, complete general-purpose send outbox, and new UI.
