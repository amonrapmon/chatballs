# Gateway Outbox Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the persisted `gateway.delivery_command.requested.v1` command from the Chatballs Outbox to `intercom-gw` with a short tenant read, an external HTTP call outside `tenant_atomic()`, existing retry semantics, and scoped PROCESSING lease recovery.

**Architecture:** Extend the existing event registry with opt-out metadata while preserving transactional defaults. Register a dedicated Conversations handler that resolves and validates the tenant-owned GATEWAY integration inside a short transaction, then sends the exact persisted command through a small `urllib` client. Extend the platform Outbox claim query to use `next_attempt_at` as a lease only for handlers explicitly marked reclaimable.

**Tech Stack:** Django, PostgreSQL/RLS tenant transactions, existing Outbox worker, Python stdlib `urllib.request`, pytest/Django tests, Docker Compose dev stack.

**Spec:** User-provided gateway handoff specification in the task message; repository contract and sequencing docs: `docs/contracts.md`, `docs/implementation-plan.md`.

## Global Constraints

- Work only in `./chatballs` on `feat/intercom-gateway` above parent `bfd0f85940c21a692d0228466587373123bbf3a6`.
- Do not modify `intercom-gw`.
- Keep the persisted Outbox `payload["command"]` as the exact HTTP JSON body and never generate a new `command_id` in the worker.
- Keep all network I/O outside `tenant_atomic()`; use a short tenant-scoped read for `Integration` only.
- Use existing `mark_retry()` and worker status transitions; do not add a second retry system or provider delivery logic.
- Preserve default registry behavior: `tenant_transaction=True`, `recover_stale_processing=False`.
- Use existing `OutboxEvent.next_attempt_at` for the PROCESSING lease; no schema migration.
- Do not add `requests`, `httpx`, media, provider sends, echo suppression, callbacks, AI replies, or polling for GATEWAY.
- Do not run the full test suite; run only focused event/conversation/integration tests plus requested checks.

---

### Task 1: Add handler metadata without changing legacy defaults

**Files:**
- Modify: `apps/backend/chatballs/events/handlers.py`
- Modify: `apps/backend/chatballs/events/services.py`
- Create: `apps/backend/chatballs/events/test_handlers.py`

**Interfaces:**
- `register(event_type, *, tenant_transaction=True, recover_stale_processing=False)` returns the decorated handler and stores its metadata.
- `get_registration(event_type)` returns the registered metadata or `None`.
- `dispatch()` uses the metadata to skip the outer `tenant_atomic()` only when `tenant_transaction=False`.
- `claim_next_outbox_event()` consults registration metadata to include expired PROCESSING events only when `recover_stale_processing=True`.

- [x] **Step 1: Write failing registry and dispatch tests**

  Cover registration, legacy default metadata, non-transactional dispatch, and transaction-wrapped legacy dispatch. Use an injected handler that records `connections["default"].in_atomic_block` and assert the GATEWAY registration can run with it false.

- [x] **Step 2: Run the focused tests and verify they fail for the missing metadata behavior**

  Run: `docker compose -f compose.yaml -f compose.dev.yaml run --rm backend-app pytest -q chatballs/events/test_handlers.py`

- [x] **Step 3: Implement the smallest metadata registry and dispatch branch**

  Keep existing decorators source-compatible. Avoid importing the registry back into the module at import time from `services.py`; use a local import in the claim path if needed to avoid a circular dependency.

- [x] **Step 4: Run the focused registry tests and verify they pass**

  Run the same command and confirm all tests pass.

---

### Task 2: Add timeout and processing lease settings

**Files:**
- Modify: `apps/backend/chatballs_backend/settings_base.py`
- Create or modify: focused settings test only if the existing settings test location requires it

**Interfaces:**
- `settings.CHATBALLS_GATEWAY_DELIVERY_TIMEOUT_SECONDS` defaults to `5` and is controlled by `CHATBALLS_GATEWAY_DELIVERY_TIMEOUT_SECONDS`.
- `settings.CHATBALLS_OUTBOX_PROCESSING_LEASE_SECONDS` defaults to `30` and is controlled by `CHATBALLS_OUTBOX_PROCESSING_LEASE_SECONDS`.
- Startup rejects non-positive values and a lease that is not greater than the gateway timeout.

- [x] **Step 1: Define the settings defaults and validation expectations**

  Assert the defaults and the lease/timeout relationship without changing existing AI timeout settings.

- [x] **Step 2: Check the repository for an isolated settings test location**

  No existing isolated settings test module was present; settings are exercised by
  the Docker-backed test configuration and startup checks below.

  Run the smallest existing settings test module or the new focused test through the backend container.

- [x] **Step 3: Add the two settings with validation**

  Place them beside the existing runtime timeout settings and use `ImproperlyConfigured` for invalid values.

- [x] **Step 4: Verify settings load and no migration is generated**

  Confirm no migration is generated by these settings.

---

### Task 3: Implement the GATEWAY HTTP client and event handler

**Files:**
- Create: `apps/backend/chatballs/conversations/gateway_http.py`
- Create: `apps/backend/chatballs/conversations/gateway_event_handlers.py`
- Modify: `apps/backend/chatballs/conversations/apps.py`
- Create: `apps/backend/chatballs/conversations/test_gateway_event_delivery.py`

**Interfaces:**
- `send_delivery_command(*, base_url: str, secret: str, command: dict) -> None` posts the exact command JSON to `{base_url.rstrip('/')}/delivery-commands` with Bearer authentication and the configured timeout.
- `handle_gateway_delivery_command_requested(payload: dict, context: TenantContext | None) -> None` validates payload shape, resolves the tenant-scoped active GATEWAY integration, verifies `command.source_id`, closes the read transaction, and calls the HTTP client.
- Errors are categorized without including the secret, Authorization header, full command, or message text in exception strings.

- [x] **Step 1: Write failing HTTP and handler tests**

  Cover registration through `ConversationsConfig.ready()`, tenant ownership, provider/active checks, source mismatch, URL normalization, decrypted secret, exact persisted command body including whitespace, response validation for only `202/accepted=true/matching command_id`, network errors, and sanitized exception strings. Add a sender seam that asserts `connections["default"].in_atomic_block is False` and separately assert Integration lookup runs under tenant context.

- [x] **Step 2: Run the focused delivery tests and verify they fail for absent handler/client behavior**

  Run: `docker compose -f compose.yaml -f compose.dev.yaml run --rm backend-app pytest -q chatballs/conversations/test_gateway_event_delivery.py`

- [x] **Step 3: Implement the stdlib HTTP client**

  Use `urllib.request.Request`, `json.dumps(command)`, `urlopen(..., timeout=settings.CHATBALLS_GATEWAY_DELIVERY_TIMEOUT_SECONDS)`, and strict response checks. Convert `HTTPError`, `URLError`, timeout/OSError, JSON decode errors, and contract mismatches into a small `GatewayDeliveryError` hierarchy with safe messages.

- [x] **Step 4: Implement the short tenant read and handler registration**

  In one `tenant_atomic(context)` load `Integration.objects.get(id=payload["integration_id"], organization=context.organization)`, validate `provider == GATEWAY` and `is_active`, copy only `base_url`, `source_id`, and decrypted `secret`, validate the persisted command source, then exit the block before invoking the client. Register with `tenant_transaction=False` and `recover_stale_processing=True`; import the module from `ConversationsConfig.ready()`.

- [x] **Step 5: Run the focused delivery tests and verify they pass**

  Confirm the network seam observes no open tenant transaction and that all invalid HTTP responses fail.

---

### Task 4: Add scoped PROCESSING lease and worker completion tests

**Files:**
- Modify: `apps/backend/chatballs/events/services.py`
- Modify: `apps/backend/chatballs/events/management/commands/run_worker.py` only if an explicit success/retry adjustment is proven necessary
- Create or modify: `apps/backend/chatballs/events/test_services.py` and/or focused worker tests

**Interfaces:**
- Initial GATEWAY claims set `status=PROCESSING` and `next_attempt_at=now + settings.CHATBALLS_OUTBOX_PROCESSING_LEASE_SECONDS`.
- Expired PROCESSING rows are claimable only when their event type is registered with `recover_stale_processing=True`.
- Non-expired PROCESSING rows and expired legacy PROCESSING rows remain unclaimable.
- Successful handler execution follows the existing worker path to `PROCESSED`; exceptions follow `mark_retry()`.

- [x] **Step 1: Write failing claim/recovery and crash-after-202 tests**

  Use real database rows and timestamps. Assert the same persisted command object and `command_id` are sent on the second claim after an injected crash between HTTP success and marking PROCESSED.

- [x] **Step 2: Run the focused event-service/worker tests and verify they fail**

  Run only the new/changed event tests and the existing focused calls/notifications dispatch tests.

- [x] **Step 3: Implement lease-aware claim selection**

  Keep PENDING/FAILED selection unchanged. Add the explicitly recoverable PROCESSING predicate, set the lease deadline on every claim, and save both fields in one platform transaction.

- [x] **Step 4: Run focused claim/retry/worker tests and verify they pass**

  Confirm legacy Calls/Notifications behavior remains unchanged.

---

### Task 5: Repository verification, commit, and push

**Files:**
- Review all changed files; no migration expected.

- [x] **Step 1: Run focused PostgreSQL-backed tests**

  Run the new gateway/event tests, existing `test_gateway_operator_reply.py`, `calls/tests/test_flow.py`, and notification dispatch tests that exercise the registry.

- [x] **Step 2: Run requested static/schema checks**

  Run targeted Ruff for changed Python files, `python manage.py makemigrations --check --dry-run`, and `git diff HEAD^ HEAD --check` from `chatballs`.

- [x] **Step 3: Inspect the final diff and status**

  Confirm only `chatballs` changed, no migration exists, no secrets/payload text appear in logs or exceptions, and the branch remains `feat/intercom-gateway` above the stated parent.

- [x] **Step 4: Commit one focused change**

  Use a message describing the gateway Outbox handoff and record the resulting SHA.

- [x] **Step 5: Push `origin/feat/intercom-gateway` and report evidence**

  Final report must distinguish changed vs verified vs not verified and include Branch, Parent commit, Commit SHA, HTTP contract, transaction-boundary proof, retry behavior, PROCESSING lease/recovery proof, legacy regression, contract deviations, and open decisions.
