# Native Mirror: cross-repository synthetic smoke

This is an **opt-in contract integration check**, not a GREEN-API live smoke.
It exercises actual TG/MAX normalizers and provider-event routing from
`intercom-gw`, maps their messages through the real Chatballs destination,
and replays that dynamically produced JSON through Django's Gateway API
against **disposable PostgreSQL**.

It does not run two deployed services over the network. The Gateway receiver
is fake while generating the bundle; Django REST APIClient is in-process
during the database checks. A real inter-container HTTP rehearsal and
provider-origin evidence still require a separate approved stage.

## Prerequisites

- Sibling repository layout: `intercom-gw/` and `chatballs/`.
- Node.js 22+ and npm dependencies already installed for `intercom-gw`.
- An **isolated**, disposable Chatballs PostgreSQL 15 / Redis 7 test
  environment. Do **not** use production Compose or production data.
- Both repositories checked out to their feature branches:
  `intercom-gw: feat/native-mirror-provenance`;
  `chatballs: feat/native-mirror-core`.
- No real GREEN-API keys or external services.

## Produce a bundle with actual TG/MAX code

From `intercom-gw/`, in PowerShell:

```powershell
git pull --ff-only origin feat/native-mirror-provenance
npm run build:tg
npm run build:max

$bundle = (Join-Path (Resolve-Path ../chatballs).Path ".artifacts/native-mirror/cross-repo.json")
node tools/native-mirror-smoke-bundle.mjs $bundle
```

The generator asserts that provider API-originated outgoing events are not
sent to the native operator mirror; a simulated HTTP 503 and redelivery must
produce identical payloads. It writes **synthetic** TG and MAX cases only.

## Run the receiving Chatballs smoke

From `chatballs/`, keeping the existing disposable `$dc` Compose argument
array (defined by the earlier isolated Native Mirror setup):

```powershell
git pull --ff-only origin feat/native-mirror-core
docker @dc build init
docker @dc up -d --wait postgres redis

$bundle = (Join-Path (Get-Location).Path ".artifacts/native-mirror/cross-repo.json")
if (-not (Test-Path $bundle)) { throw "Missing synthetic Gateway bundle" }

docker @dc run --rm --no-deps `
    -v "${bundle}:/tmp/native-mirror-smoke.json:ro" `
    -e CHATBALLS_NATIVE_SMOKE_BUNDLE=/tmp/native-mirror-smoke.json `
    init pytest -q --reuse-db chatballs/native_mirror/smoke_cross_repo.py
```

No new migrations were introduced for this smoke. It runs six focused test
methods, each evaluating both TG and MAX, and uses `--reuse-db`. The smoke
is named `smoke_cross_repo.py` so the default `test_*.py` suites do not
silently require the external JSON.

## Protected behavior

- `SHADOW` leaves AI turns and visible conversation state unchanged.
- `ENABLED` stores one authorized native reply, supersedes old PENDING work,
  and keeps AI control for the next customer turn (revision increases once).
- Duplicate/replayed events do not duplicate messages or revision increments.
- Events received before a matching conversation are retained and processed
  after the conversation is created.
- Correlated own outgoing messages are recognized as echoes.
- A queued Gateway AI answer, which becomes stale before publication claim,
  is suppressed, not submitted to external HTTP.
- Wrong bearer/source does not create native receipt state.

This does **not** validate real GREEN-API callback provenance, a live
connector cursor, actual container-to-container networking, or production
authorization. Feature flags remain untouched.
