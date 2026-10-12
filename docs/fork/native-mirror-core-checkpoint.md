# Native Mirror Core: contracts checkpoint (2026-10-12)

Branch: `feat/native-mirror-core`, from `feat/native-reply-extension` at `84cb117`.

## Implemented in this checkpoint

- Additive and inert `native_mirror` module: validated text reply event, typed outcome,
  safe per-integration mode parsing, conservative evidence classification.
- No runtime hook, database schema, HTTP endpoint, poller change or migration.
  Production and current TG/MAX legacy mirror behavior are unchanged.
- Pure targeted tests in `native_mirror/test_contracts.py`; execution pending
  until run with the existing disposable Docker setup.

## Deliberately not claimed as implemented

- Transactional `accept()` service with durable dedup/revision/processing outcome.
- Tenant-scoped schema, permissions, RLS, rollback, ambiguous-chat policy.
- Sender authorization / source mapping / self-echo provider correlation.
- AI supersession, publication claim, VK Long Poll or Gateway adapter.

This checkpoint does not satisfy Stage 1 / Gate S1 yet. The approved
architecture choices for per-conversation revision and durable inbox must be
settled before implementing the DB-backed service. Only authenticated,
server-verified evidence may be used to classify external authors.
