# CRM Bridge v1: UI baseline proposal

Status: **approved by owner, 2026-10-15**. Product UI implementation is tracked separately.

- `Настройки CRM.dc.html`: existing Settings → Organization layout, an additional CRM card. Scenarios: one branch / multiple branches / CRM off.
- `Контакты и диалог.dc.html`: direct CRM search link in narrow conversation contact sidebar and global contact header. Scenarios: one branch / multiple branches / missing binding / missing phone.
- `baseline.css`: styles for preview only, aligned to existing Chatballs v2 geometry, typography and blue-accent treatment. It is *not* a new frontend design system.

## Proposed behavior

1. Do not add a new Settings subnav item. CRM controls live in an independent card below Organization settings.
2. Provider choices: None / YCLIENTS / DIKIDI. Display the external CRM company ID explicitly. The primary company is editable as a CRMCompany field, not stored in upstream Organization.
3. One active branch: show the link without configuring each messenger. More than one: map integrations to branches; never silently choose primary for an unbound dialog.
4. Conversation context: compact `.link.has-icon` near contact phone with label `Профиль DIKIDI` or `Профиль YCLIENTS`, plus the resolved company label.
5. Global contact header: one branch -> direct link, more than one -> antd Dropdown with explicit branch names (and messenger sources). No arbitrary CRM website or direct CRM client card URL.
6. No phone, CRM disabled: no link. Missing/ambiguous branch: plain explanation, no clickable CRM link; only admins get a settings action.
7. External links open in a new tab (`target="_blank"`, `rel="noopener noreferrer"`) after backend resolves a trusted URL.
8. Owner/admin can manage CRM settings. Staff see only links allowed by their conversation visibility.
9. Narrow/mobile layout should reuse the existing settings subnav/back navigation and client-card breakpoints; these HTML previews show the visual intent, not the final responsive product implementation.
10. All real UI copy goes into `src/i18n` with ru/en parity during product implementation.

## Important notes

All names, IDs and phones in the preview are **illustrative**. The implementation must only use real organization/integration/contact values from API.
The demonstration-only toolbar outside the workspace is not part of product UI.
No backend or frontend actions are performed by these local HTML previews.