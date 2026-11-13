# GEN-208 · upstream boundary inventory (baseline 2026-11-13)

**Status: verified tree-level inventory, NOT an implementation PR or completed upgrade rehearsal.**
**Source:** GitHub repository trees, recursively traversed and compared by full path and blob SHA, without the 300-file REST compare limit.

| Side | Commit | Tree |
| --- | --- | --- |
| upstream `dartdavros/chatballs` main | `0764cad1dd29dd54732e25c59939d9b3f982a1d3` | `614fde625e26be34e3c29a7aeb30d91810bff510` |
| fork `amonrapmon/chatballs` main | `663f07a302079dd34f431ff04649651e0be08710` | `6ef0f3ac9dbd0f9075fb5bb86fc48d34000680c5` |

GitHub compare commits reports **344 ahead / 0 behind**. Exact tree comparison reports **212 added, 97 modified, 0 removed = 309 different tracked blobs**. The REST compare API shows at most 300 files; use this baseline instead.

## Inventory by area

| Area (first matching directory classification) | Added | Modified existing | Removed |
| --- | ---: | ---: | ---: |
| Connector backend | 28 | 0 | 0 |
| Integrations backend | 11 | 10 | 0 |
| Conversations core | 36 | 43 | 0 |
| Other backend | 82 | 9 | 0 |
| Internal UI | 22 | 28 | 0 |
| Contracts | 7 | 0 | 0 |
| CI workflows | 5 | 1 | 0 |
| Other infra/docs | 21 | 6 | 0 |

**Interpretation:** The 28 Connector backend files are entirely new to the fork at these commits, which is promising for extraction. But **81 existing core/UI files** are modified in Conversations, Integrations and Internal UI alone; each requires a separate neutral-change audit before an upstream-friendly merge. File counts are a conflict-risk indicator, not proof of Connector-only ownership. Service adapters and other unrelated features also contribute to this diff.

## Modified existing files (highest upstream conflict risk)

### Integrations backend (10 modified existing files)
- `apps/backend/chatballs/integrations/checking.py`
- `apps/backend/chatballs/integrations/checks.py`
- `apps/backend/chatballs/integrations/execution/payloads.py`
- `apps/backend/chatballs/integrations/execution/test_ai_runtime.py`
- `apps/backend/chatballs/integrations/management.py`
- `apps/backend/chatballs/integrations/models.py`
- `apps/backend/chatballs/integrations/serializers.py`
- `apps/backend/chatballs/integrations/services.py`
- `apps/backend/chatballs/integrations/urls.py`
- `apps/backend/chatballs/integrations/views.py`

### Conversations core (43 modified existing files)
- `apps/backend/chatballs/conversations/ai_reply_delivery.py`
- `apps/backend/chatballs/conversations/ai_turn.py`
- `apps/backend/chatballs/conversations/ai_turn_completion.py`
- `apps/backend/chatballs/conversations/ai_turn_result.py`
- `apps/backend/chatballs/conversations/ai_turn_state.py`
- `apps/backend/chatballs/conversations/apps.py`
- `apps/backend/chatballs/conversations/attachment_send.py`
- `apps/backend/chatballs/conversations/client_common.py`
- `apps/backend/chatballs/conversations/client_details.py`
- `apps/backend/chatballs/conversations/clients.py`
- `apps/backend/chatballs/conversations/contact_models.py`
- `apps/backend/chatballs/conversations/conversation_models.py`
- `apps/backend/chatballs/conversations/domain_event_models.py`
- `apps/backend/chatballs/conversations/escalation.py`
- `apps/backend/chatballs/conversations/event_handlers.py`
- `apps/backend/chatballs/conversations/inbound_dedup.py`
- `apps/backend/chatballs/conversations/ingest.py`
- `apps/backend/chatballs/conversations/list_queries.py`
- `apps/backend/chatballs/conversations/message_history.py`
- `apps/backend/chatballs/conversations/message_models.py`
- `apps/backend/chatballs/conversations/message_views.py`
- `apps/backend/chatballs/conversations/models.py`
- `apps/backend/chatballs/conversations/operator_messages.py`
- `apps/backend/chatballs/conversations/operator_reply.py`
- `apps/backend/chatballs/conversations/poller.py`
- `apps/backend/chatballs/conversations/selectors.py`
- `apps/backend/chatballs/conversations/serializer_context.py`
- `apps/backend/chatballs/conversations/serializers.py`
- `apps/backend/chatballs/conversations/service_common.py`
- `apps/backend/chatballs/conversations/test_ai_turn.py`
- `apps/backend/chatballs/conversations/test_clients_list.py`
- `apps/backend/chatballs/conversations/test_contact_avatars.py`
- `apps/backend/chatballs/conversations/test_domain_event_guards.py`
- `apps/backend/chatballs/conversations/test_ingest_dedup.py`
- `apps/backend/chatballs/conversations/test_poll_backoff.py`
- `apps/backend/chatballs/conversations/test_vk_transport.py`
- `apps/backend/chatballs/conversations/transports/base.py`
- `apps/backend/chatballs/conversations/transports/vk.py`
- `apps/backend/chatballs/conversations/transports/vk_send.py`
- `apps/backend/chatballs/conversations/upload_paths.py`
- `apps/backend/chatballs/conversations/urls.py`
- `apps/backend/chatballs/conversations/voice_send.py`
- `apps/backend/chatballs/conversations/voice_testing.py`

### Other backend (9 modified existing files)
- `apps/backend/chatballs/events/management/commands/run_worker.py`
- `apps/backend/chatballs/i18n/messages/en.py`
- `apps/backend/chatballs/i18n/messages/ru.py`
- `apps/backend/chatballs/identity/audit_catalog.py`
- `apps/backend/chatballs/identity/company_urls.py`
- `apps/backend/chatballs/tenancy/ingress.py`
- `apps/backend/chatballs/webchat/message_selectors.py`
- `apps/backend/chatballs_backend/settings_base.py`
- `apps/backend/chatballs_backend/urls_app.py`

### Internal UI (28 modified existing files)
- `apps/internal-ui/src/features/conversations/FileMessage.tsx`
- `apps/internal-ui/src/features/conversations/VoiceMessage.tsx`
- `apps/internal-ui/src/features/conversations/apiTypes.ts`
- `apps/internal-ui/src/features/conversations/conversationApi.ts`
- `apps/internal-ui/src/features/conversations/history-layout.css`
- `apps/internal-ui/src/features/conversations/model.ts`
- `apps/internal-ui/src/features/conversations/types.ts`
- `apps/internal-ui/src/features/conversations/useConversationFeed.ts`
- `apps/internal-ui/src/features/conversations/useHistoryWindow.ts`
- `apps/internal-ui/src/features/integrations/ConnectionsTable.tsx`
- `apps/internal-ui/src/features/integrations/IntegrationForm.tsx`
- `apps/internal-ui/src/features/integrations/model.test.ts`
- `apps/internal-ui/src/features/integrations/model.ts`
- `apps/internal-ui/src/features/integrations/rows.tsx`
- `apps/internal-ui/src/features/integrations/useIntegrationForm.ts`
- `apps/internal-ui/src/features/integrations/workspaceModel.test.tsx`
- `apps/internal-ui/src/features/integrations/workspaceModel.ts`
- `apps/internal-ui/src/features/sales/client-detail/SalesClientHeader.tsx`
- `apps/internal-ui/src/features/sales/client-detail/SalesClientIdentitiesTab.tsx`
- `apps/internal-ui/src/features/sales/client-detail/model.ts`
- `apps/internal-ui/src/features/sales/clients/model.ts`
- `apps/internal-ui/src/features/sales/dialogs/context/ClientContext.tsx`
- `apps/internal-ui/src/features/settings/SettingsPage.tsx`
- `apps/internal-ui/src/i18n/en.ts`
- `apps/internal-ui/src/i18n/ru.ts`
- `apps/internal-ui/src/shared/badges.tsx`
- `apps/internal-ui/src/shared/links.css`
- `apps/internal-ui/src/shared/providers.ts`

### CI workflows (1 modified existing files)
- `.github/workflows/checks.yml`

### Other infra/docs (6 modified existing files)
- `docs/verification/T-155/backend-build.log`
- `docs/verification/T-163/frontend-tests.txt`
- `docs/verification/T-163/renderer-tests.txt`
- `docs/verification/T-163/structure.txt`
- `docs/verification/T-163/ui-typecheck.txt`
- `docs/verification/T-163/widget-tests.txt`

## Existing mechanism to reuse, not rebuild

The fork already has the generic service adapter descriptor, TypeSpec and renderer machinery:
- Backend `integrations/adapters/{schema,contracts,registry}.py`, `integrations/service_connections/{services,payloads,checks}.py`.
- Frontend `integrations/services/connect/{SchemaFields,fieldControls,useConnectForm}.tsx`.
- **Do not** reuse the `ADAPTER`/kind=`SERVICE` Integration record for messenger connections: it has no Channel/Inbox runtime. Reuse only the declarative field schema/validation/renderer; messenger transport remains `API_CONNECTOR` Integration with existing Conversation/ConnectionIdentity foreign keys.
- First service manifest: `Green API`, platform `MAX|TELEGRAM`, credentials `idInstance,apiTokenInstance,apiUrl,mediaUrl`; provider credentials flow only into encrypted adapter registry.

## Next executable gates

1. Review every one of the modified-existing file paths above and classify keep/neutralize/drop/obsolete using actual contents, not naming.
2. Split neutral Connector code from provider-specific adapter and obsolete native mirror patches. No Green API SDK/credential in Chatballs core.
3. Build a slim branch from a clean, pinned upstream base, then run per-file/contract tests and native regression before declaring upgrade compatibility.
4. Maintain legacy Integration config (`green_api_telegram/max/custom_adapter`) and existing wire identities. No direct SQL patch, no new Chatballs DB migration solely for UI.
5. Compare real runner output, not check conclusion only. **GitHub Actions in adapter PR #24 currently fail before steps start**; this is an unresolved CI infrastructure gate, not test failure evidence.

**Related:** GEN-42, GEN-22, GEN-56, GEN-57, GEN-196, GEN-208. Do not publish or merge upstream PR without explicit later approval.
