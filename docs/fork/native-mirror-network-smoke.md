# TG/MAX Native Mirror: private Docker HTTP smoke

This opt-in test exercises **real HTTP over a private Docker Compose network**
between the existing Chatballs Django gateway ingress and actual TG/MAX
Fastify callback handlers + Chatballs destination classes.

There are three test containers:
- `native-smoke-runner`: Django `LiveServerTestCase`, using disposable
  PostgreSQL test database from the existing `cb-native-mirror-test` project;
- `native-smoke-tg`: TG Fastify HTTP app;
- `native-smoke-max`: MAX Fastify HTTP app.

The TG/MAX services use a strictly in-memory, test-only repository for
provider reconciliation and raw-event error counters. Their normalizers,
callback routing, HTTP destination client and delivery-command endpoint are
**production code**. No real GREEN-API or SMTP/AI provider calls, real tokens,
shared `intercom_private`/proxy networks or host port publishing.

This is an **HTTP integration rehearsal**, not full durable Gateway PostgreSQL
or live provider callback verification. The regular intercom-gw DB integration
tests cover that part separately.

## Prerequisites

- Sibling checkout folders `chatballs/` and `intercom-gw/` in the same
  directory. Update these two feature branches first.
- PowerShell Docker Compose array `$dc` already configured for the
  **disposable** `cb-native-mirror-test` instance, including the port reset
  override and the same data-directory env variables from prior tests.
  Do not use a production project, production secrets or bind mounts.
- Docker Desktop with working Linux containers.
- Existing test PostgreSQL / Redis started under `$dc`.
- Do not run all services from canonical compose.

## Run from the Chatballs repository root

```powershell
# From chatballs/
git pull --ff-only origin feat/native-mirror-core
docker @dc build init
docker @dc up -d --wait postgres redis

# Test-only services share the same isolated Compose project/network.
$netdc = $dc + @("-f", "compose.native-mirror-network-smoke.yaml")
docker @netdc config --services
docker @netdc build native-smoke-tg native-smoke-max
docker @netdc up -d --wait native-smoke-tg native-smoke-max
docker @netdc ps

# --use-aliases is essential: Gateway reaches the live Django test server
# at native-smoke-runner:<ephemeral LiveServer port> over private DNS.
docker @netdc run --rm --no-deps --use-aliases native-smoke-runner
```

Expected: four opt-in Django methods, each exercises **both** TG and MAX,
with the real HTTP response codes, synthetic auth, bridge transport and
PostgreSQL state all asserted.

Protected scenarios:
1. Authenticated inbound and native outbound webhook routes.
2. `SHADOW` remains non-mutating, then `ENABLED` dedupes, supersedes AI,
   and allows a fresh AI-turn request with updated revision.
3. Wrong webhook token returns HTTP 403; wrong Chatballs bearer returns
   downstream HTTP 401 (Gateway retains a failed raw event).
4. One injected HTTP 503 and exact raw webhook retry eventually produce one
   canonical native reply, not duplicates.
5. Native reply before outbound publication prevents network dispatch.
6. The existing Gateway delivery-command HTTP endpoint authenticates bearer
   token, rejects bad source, accepts a valid synthetic command. It is
   **recorded in memory**, never sent to GREEN-API.

The test listener binds to `0.0.0.0` inside its container on a random port
and is not published to the host. Gateway's private `/__smoke/*` endpoints
exist only in the standalone test image, never normal runtimes.

## Inspect and stop only the two smoke sidecars

```powershell
docker @netdc logs --tail 80 native-smoke-tg native-smoke-max
docker @netdc stop native-smoke-tg native-smoke-max
```

Do **not** use `down -v`, delete PG volumes, or stop live deployments.
No schema migrations or `--create-db` are needed by this test.

If a test fails, report the first actual assertion / traceback and the
`native-smoke-*` healthchecks. Do not paste secrets or full raw webhooks.

## Remaining outside this smoke

- Real GREEN-API callback provenance and event subscription behavior;
- production Gateway database claim, replay and cross-worker persistence
  (already separately tested at lower layer but not here);
- actual live model response or real external send;
- one controlled `SHADOW` trial on a **test integration**, after explicit
  rollout approval. No rollout or user-facing config modification is implied.
