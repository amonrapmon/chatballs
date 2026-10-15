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

## Still required before declaring CRM Bridge v1 complete

- Database migration validation (`makemigrations --check --dry-run`, `migrate --plan`, RLS, tenant grants, PostgreSQL tests).
- Transactional service operations for switching providers, primary company management and binding validation.
- Permission-aware tenant-scoped API with contact/conversation visibility checks.
- Approved `design/baseline` and then UI implementation.
- Integration, regressions, review and deployment approval.

**Safety:** do not run these migrations in production or treat schema code as release-ready until the real database checks pass.
