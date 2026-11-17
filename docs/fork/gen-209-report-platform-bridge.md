# GEN-209: report platform bridge (no event-schema changes)

## Boundary

Chatballs keeps its authoritative transport as `Integration.provider`. An `API_CONNECTOR` Integration remains `API_CONNECTOR` for routing, `ConversationEvent.transport`, validation, history and exports.

The existing `display_provider(Integration)` resolver is **presentation metadata only**, based on `config.connector_service` for supported adapters. The report directory exposes this as an additional `displayProvider` field without changing the existing `provider` response. Its existing visibility, tenant isolation and reporting roles remain the security boundary.

No event writer/validator, database table, migration, Channel assignment, employee group or report aggregation routine is modified.

**Historical limitation:** `displayProvider` is derived from the *current* `Integration.config.connector_service`. The current `update_integration` path permits changes to this selector, while older `ConversationEvent` snapshots retain only `API_CONNECTOR` + `connection_id`. If an Integration is repurposed from Telegram to MAX, this projection **cannot** reconstruct historical messenger identities. Until connector-service immutability or versioned attribution is enforced by the host/adapter contract, keep each Integration bound to one messenger for its lifetime and do not claim messenger-accurate history after reassignment. No historical events are relabeled by this bridge.

## User-facing behavior

- Overview `byChannel` already includes API Connector conversations, grouped by their assigned Channel. This is **not** a global messenger-type group. Channel defines AI context and access, so *do not* move integrations between channels for reporting.
- Report filter "Мессенджер" recognizes an effective platform (native and Connector-derived), then filters its available, report-visible connections.
- One Connector integration for a platform: choose its real `connection` ID and `transport=API_CONNECTOR`. Existing HTTP report, daily charts and CSV/XLSX all use that same pair. Historic facts remain attributed to the technical transport.
- Multiple connections sharing a messenger when at least one is via Connector: **require a specific connection** rather than rendering a false messenger-wide total. Do not issue an unfiltered query and do not enable export while selection is required.
- A platform containing only native integrations retains the existing transport-wide filtering; an ordinary generic `API_CONNECTOR` selection must never include branded Telegram/MAX integrations as a fabricated "generic Connector" aggregate.
- Native filters without a selected messenger and by-connection reports still work as before.

## Why no combined TG/MAX employee report yet?

The existing support report API accepts exactly one `connection` ID and one historical `transport`. It does **not** accept a set of connections or an effective-messenger dimension. Summing separately returned JSON/CSV/XLSX reports would corrupt uniqueness, interval averages, feedback and potentially current-load values. Channel is an AI/work-access entity, not a messenger dimension; employee group is an authorization entity, not a transport filter.

To deliver exact platform-wide totals across multiple connections, implement a **neutral** upstream extension accepting a scoped list of connection IDs/effective platform, or a separate read-model that can consume individual historical facts with the same tenant/role constraints. That is **not** part of this bridge. Do not patch the event transport or quietly merge per-connection aggregates.

## Upgrade and regression gate

1. UI tests: native Telegram + Connector Telegram; single MAX; unknown connector; generic API Connector; historical filter parameters; switching platform/connection.
2. Backend test: report directory outputs both fields, original provider stays unchanged.
3. Run frontend `typecheck`, `test`, `build` and backend `test_report_directory_platform` on the isolated Lab runner. GitHub-hosted Actions currently have a billing blocker; no PASS may be claimed without logs.
4. Confirm JSON/CSV/XLSX match one Connector connection, and that several TG integrations prompt selection. Confirm supervisor visibility and cross-tenant isolation with real test data.
5. Remain Draft and out of main/production until explicit approval, Lab evidence and GEN-209 real E2E gates.

Related: GEN-208 (upstream seam / upgrade rehearsal), GEN-209 (Telegram+MAX self-service).
