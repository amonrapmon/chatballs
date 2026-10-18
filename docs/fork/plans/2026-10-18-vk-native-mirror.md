# VK Native Mirror: implementation plan

**Status:** implementation plan, runtime changes not started (2026-10-18).  
**Repository:** `amonrapmon/chatballs`. **Base:** current `main`.  
**Working branch:** `feat/vk-native-mirror`.  
**Related documents:** `docs/fork/plans/native-reply-extension.md`, `docs/fork/upstream-compatibility.md`.  
**Scope:** VK only. This document supersedes the older VK-stage design where it conflicts with the decisions below; it does not revise TG/MAX Gateway behavior.

## 1. Goal and fixed decisions

Deliver outgoing messages written in the **native VK community interface** into the existing Chatballs conversation, labeled **VK Native**.

- Use **the existing VK Bots Long Poll**, with one consumer and one `ts` per community connection. Never create a second poller, Callback receiver or VK gateway.
- `message_new` keeps the current Chatballs inbound path; `message_reply` goes to a thin VK mirror adapter.
- A VK-native reply becomes a normal `Message(author_type=OPERATOR)` in the matching existing `Conversation` with technical author **VK Native**.
- **Do not identify, fetch, map or display actual VK administrators.** Their VK ID has no business value for v1. The technical author identifies the transport origin, not a named human.
- Reuse `native_mirror` receipts, deduplication, replay and revision/supersession. Do not build a second conversation store or native mirror core.
- `control_mode` is never switched by the mirror.
- Do not connect or activate an AI agent until the mirror alone works on the test connection.
- Do not modify TG/MAX through `intercom-gw`, add statistics or redesign the UI.
- Keep upstream changes tiny; new VK-specific behavior should live in `native_mirror/vk_adapter.py` and adjacent isolated helpers.

**Two message origins must not be confused:**

1. Reply written in native VK: store once as `VK Native`.
2. Reply sent **from Chatballs** using VK `messages.send`: already exists as a Chatballs message; the `message_reply` echo must **not** create another message or interrupt AI.

No correlation of *employees* is needed. Correlation of *our own outbound messages* is needed only to avoid echo duplicates and false AI supersession.

## 2. Current verified integration points

| File | Existing behavior | Small required change |
| --- | --- | --- |
| `conversations/transports/vk.py` | `poll_updates` returns only normalized `message_new`; `message_reply` is ignored | Add typed native-reply extraction in the same VK poll result; keep the inbound parser unchanged |
| `conversations/transports/__init__.py` | `poll()` forwards a transport batch with backoff | Keep other providers' contract and backoff unchanged; adapt VK result only as necessary |
| `conversations/poller.py` | Logs individual ingest errors but advances `poll_marker` after the batch | Dispatch VK native events and prevent cursor advancement when required handling failed |
| `conversations/transports/vk_send.py` | `messages.send` response is discarded; public send API returns `bool` | Capture returned VK message ID in a narrow internal path while retaining existing bool callers |
| `conversations/operator_messages.py` | Saves operator message and calls generic `send_reply` | Associate local operator `Message` with provider message ID for VK-only outbound |
| `conversations/ai_reply_delivery.py` | Saved AI response sent through generic `send_reply`, checks `mirrorRevision` | Capture VK-only send ID for own echo; keep existing delivery and revision checks |
| `native_mirror/service.py` | Verifies `source_id` and membership; stores authorized replies with revision/supersession | Narrow provider=VK adaptation to source validation and technical author; do not weaken Gateway path |
| `native_mirror/policy.py` | Supports LEGACY, DISABLED, SHADOW, ENABLED | Reuse per-integration mode; absent/invalid setting does not enable mirror |

Relevant existing code: `native_mirror/{contracts,classification,models,storage,replay,supersession}.py`. Reuse it rather than cloning logic.

**VK source identity:** the community is currently represented by `Integration.config["bot_id"]`. The adapter must use the existing verified integration/community association as `NativeReplyEvent.source_id`; do **not** require a second unrelated VK `source_id` setting or query admin profiles. Gateway `source_id` handling remains untouched.

**Technical author:** the canonical service currently requires an active `OrganizationMembership` for an `EXTERNAL_AUTHORIZED` author. Resolve this with an organization-scoped **VK Native** technical identity, not a real employee mapping. Provisioning/changing production users or permissions is outside this task without separate owner authorization. If a technical identity cannot be supplied safely, stop at SHADOW rather than bypassing membership validation.

## 3. Processing boundary

```text
Existing VK Bots Long Poll (one ts)
   |
   +-- message_new ------> existing ingest_inbound()
   |
   +-- message_reply ----> native_mirror/vk_adapter.py
                              |
                              +-- known Chatballs echo -> suppress duplicate
                              +-- unresolved own-echo race -> hold/retry, no supersession
                              +-- VK-native reply -> accept_native_reply()
                                                   -> Message: VK Native
                                                   -> existing receipt/revision
```

For v1, route by **integration + peer_id** to one existing open conversation; never create a new customer/contact from a native reply and never guess between ambiguous conversations.

A message without matching open conversation must not be written into an arbitrary chat. Use the existing durable `PENDING` receipt/replay path once the origin is established. A message with content unsupported by the current Chatballs display must not silently disappear: reuse the existing unsupported-attachment fallback where appropriate; full VK media parity is a separate scope.

### Cursor rule

**Advance `poll_marker` only after the batch has been accepted successfully** (processed, idempotently recognized or durably staged where appropriate). If required ingestion/staging throws, keep the prior marker and retry the batch. Already completed events must remain safe to replay via their existing dedup keys.

This is the minimum acceptable fix, not a request for a new general-purpose event bus. Do not create a durable generic queue by default. Reassess only if a concrete poison-event or availability case shows the simple policy insufficient.

Protect against multiple simultaneous pollers using the same community and different positions. A second Integration with the same VK community must not silently start an independent stream.

## 4. Delivery stages and commits

### A. Real VK events, read-only SHADOW

1. Confirm `message_reply` is enabled in the **test** VK community via `groups.getLongPollSettings` / community settings; do not alter the working community.
2. Exercise one native manual reply and one send through Chatballs. Inspect **sanitized** event shape: type, `id`, `peer_id`, optional `conversation_message_id`, and response identifier of `messages.send`.
3. Add native-event normalization to the existing `vk.poll_updates`; preserve event order within a batch. Keep `message_new` path and `users.get` profile behavior intact.
4. In SHADOW, log metadata/decisions only, no Chatballs message or AI changes. Do not log tokens, private message text or unnecessary VK admin IDs.

**Commit:** `feat(vk-mirror): recognize native reply events in existing poll`  
**Gate A:** typed `message_reply` visible from the *same* poll, `message_new` unchanged, no second poller.

### B. Safe VK cursor acknowledgement

1. Route normalized VK native events from `conversations/poller.py` to the VK adapter without modifying other transport flows.
2. Stop advancing VK `poll_marker` if handling any required event fails. Keep successes idempotent on re-read; preserve existing backoff behavior.
3. Do not acknowledge an unstored ENABLED native event merely because its conversation is unavailable: rely on a committed pending receipt/replay.
4. Add a focused regression for `message_new + message_reply` in one batch, including an exception and retry/restart.

**Commit:** `fix(vk-mirror): advance cursor only after safe processing`  
**Gate B:** a failed ingest does not lose either event; a re-read does not add duplicates.

### C. Ignore our own VK echo

1. Capture the message ID returned by VK `messages.send`. Store the minimal **own-send** association scoped by integration/peer/message ID and local Chatballs Message.
2. Cover the actual VK send paths used by Chatballs: operator text, AI text and any call/file messages that emit `message_reply`. Preserve public boolean send signatures for other callers.
3. If `message_reply` arrives before the send ID association is committed, leave it **unresolved** for later matching. Do not immediately label it VK Native.
4. If the send response is missing/ambiguous, do not infer that an unmatched event is a human takeover. No text-based matching, VK admin identity lookup or random guessing.

**Commit:** `feat(vk-mirror): correlate Chatballs sends and suppress echoes`  
**Gate C:** own sends do not duplicate; echo-before-binding does not create a false native reply/supersession.

### D. Persist verified VK-native replies

1. Implement `native_mirror/vk_adapter.py` as the only VK-to-core translator.
2. Check active integration, community/source, tenant, conversation target, message ID and mode.
3. Supply technical `VK Native` author to the existing `accept_native_reply()`, using tenant-scoped authorization; preserve existing Gateway checks.
4. Reuse current `NativeMirrorReceipt` uniqueness, replay, transaction, revision and `supersede_active_turns`. No automatic `control_mode` change.
5. Do not turn a still-unresolved echo into a verified native reply.

**Commit:** `feat(vk-mirror): persist native replies through shared mirror core`  
**Gate D:** one native reply becomes one canonical OPERATOR message labeled VK Native; same event twice stays one message; no cross-tenant or wrong-chat write.

### E. Isolated verification and rollout

1. Run only targeted tests, with `--reuse-db` where appropriate. Do not run the entire suite without owner instruction.
2. Test: mixed event batch; native answer; self echo (operator, AI and relevant call/file path); duplicate/restart; race; missing/ambiguous conversation; two tenants; old VK channel; unchanged TG/MAX.
3. Test VK connection modes: default LEGACY/DISABLED unchanged, SHADOW diagnostics only, ENABLED mirrors.
4. Enable **ENABLED only for the test VK connection** after owner approval of runtime configuration. Do not deploy, edit credentials, add users or change production on your own.
5. Document what changed in upstream hooks and their targeted regressions in `docs/fork/upstream-compatibility.md` before merging to main.

**Commit:** `test(vk-mirror): verify native mirror and upstream regressions`  
**Gate E:** all acceptance scenarios below pass; release/merge requires owner review.

## 5. Acceptance matrix

- [ ] Existing VK `message_new` reaches Chatballs with original behavior.
- [ ] One native VK reply appears **once** in the correct existing conversation.
- [ ] Technical author displayed as **VK Native**; no individual staff mapping.
- [ ] VK echo of a Chatballs reply creates no duplicate and no AI supersession.
- [ ] Unknown origin is not silently promoted into `VK Native`.
- [ ] Exceptions and restarts do not silently lose a required event after advancing `ts`.
- [ ] Native reply records canonical receipt and updates conversation revision.
- [ ] Previous pending/running AI-turn becomes stale through the shared core; `control_mode` remains unchanged.
- [ ] Missing/ambiguous conversation and tenant mismatch cannot create a message in a wrong chat.
- [ ] Working VK channel and TG/MAX operate as before with mirror disabled.
- [ ] No second VK Long Poll, new `intercom-gw` VK implementation or upstream transport rewrite.

Suggested focused tests: `conversations/test_vk_transport.py`, `conversations/test_poll_backoff.py`, a new small VK adapter/poller test, `native_mirror/test_persistence.py`, `native_mirror/test_supersession.py`, and only relevant delivery tests. Existing `AGENTS.md` rules for tests and production apply.

## 6. Deferred stage F: AI experiments (not part of A–E)

After mirror-only verification, attach AI **on the test channel** and check native takeover, stale response suppression at the actual VK send boundary, preserved conversation context and eventual controlled AI resume. The last behavior is a **new, separately approved policy**, not part of the VK Mirror transport implementation.

No promise that a response already accepted by VK can be rolled back. Do not expand A–E into new agent control policies, stats, employee attribution or an alternative delivery framework.

## 7. Immediate next action

Start with **A**, then **B**. Keep commits small and independently testable. Do not implement C–F while A/B gates are unverified. Report live VK payload gaps instead of inventing event fields or administrative identities.
