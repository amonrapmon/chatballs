# CRM Bridge v1: implementation worklog

**Base:** `feat/native-mirror-core` at `dbd1a722eaaa36c5f2dd16ba8d65c4a866d47324`.  
**Feature branch:** `feat/crm-bridge-v1`.

## Confirmed upstream integration points

- `Conversation.connection` refers to `Integration`; `Integration.organization` is the owner of the messenger connection.
- `Contact.phone` is used only for building a search link. It is not a CRM identity key.
- `TenantRelationModel` validates related organization IDs in model save/clean.
- PostgreSQL has `chatballs.enforce_tenant_fk` and tenant RLS policies.
- `settings_base.py` has the installed-app list; a new app can be registered without changing upstream domain models.
- Future API should live under tenant-aware `company/crm/` routing; no API endpoint or UI is added at this stage.

## Delivered in this iteration

- Separate persistence models: organization provider, CRM companies, integration bindings.
- Own schema migrations and PostgreSQL RLS/tenant FK guards.
- Centralized DIKIDI/YCLIENTS search URL builder and focused unit tests.
- Read-only configuration and link endpoints; link resolution requires visible conversations and never guesses among multiple companies.

## Still required before declaring CRM Bridge v1 complete

- Database migration validation (`makemigrations --check --dry-run`, `migrate --plan`, RLS, tenant grants, PostgreSQL tests).
- Transactional service operations for switching providers, primary company management and binding validation.
- Writable configuration API and integration tests; read-only link endpoints are present and await Django/PostgreSQL verification.
- Approved `design/baseline` and then UI implementation.
- Integration, regressions, review and deployment approval.

**Safety:** do not run these migrations in production or treat schema code as release-ready until the real database checks pass.

## Implementation progress after CRM-04

- CRM configuration writes are exposed through tenant-scoped provider, company and integration-binding endpoints.
- Provider disable/resume retains the last active provider to avoid reinterpreting external company IDs.
- Company changes and binding changes serialize on the Organization row, use atomic transactions, and write native audit events; event labels have ru/en translations.
- Tests cover permissions, multiple CRM branches, disabling, ambiguous contacts, DB tenant FK guards, and RLS policy/grants.
- Binding deletion cascades when the associated messenger Integration is removed; CRMCompany deletion remains protected while bindings exist.

**Not executed here:** the environment has no project checkout, PostgreSQL, or Django packages; no backend tests, migrations, or checks have been executed. This PR remains draft and must be validated in the project Docker test environment before merge.

**Next gate:** run only targeted `crm_bridge` tests, `makemigrations --check --dry-run`, `migrate --plan`, verify actual migrations/RLS, and review regressions around deletion of integrations. UI still needs an approved baseline.
