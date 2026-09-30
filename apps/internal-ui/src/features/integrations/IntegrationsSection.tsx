import { useState } from "react";

import { api } from "../../api/client";
import { DeleteIntegrationDialog } from "./DeleteIntegrationDialog";
import { EmptyState } from "../../shared/ui";
import { ConnectionsTable } from "./ConnectionsTable";
import type { Integration, IntegrationKind } from "./model";
import { ProvidersTable } from "./ProvidersTable";
import { t } from "../../i18n";

// Таблица интеграций одного рода — раздел экрана «Настройки» (дизайн-базлайн v2,
// кадры N3/N4): подключения (MESSENGER) и AI-провайдеры (LLM_PROVIDER) — два
// раздела субменю. Список грузит страница настроек (счётчики в субменю), форма
// создания открывается primary-кнопкой в шапке раздела.

export function IntegrationsSection({ kind, items, reload, onEdit }: {
  kind: IntegrationKind;
  items: Integration[];
  reload: () => void;
  onEdit: (integration: Integration) => void;
}) {
  const [testingId, setTestingId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<Integration | null>(null);

  async function test(integration: Integration) {
    setTestingId(integration.id);
    try {
      await api(`/api/v1/integrations/${integration.id}/test/`, { method: "POST" });
    } catch {
      /* статус придёт из перезагрузки списка */
    } finally {
      setTestingId(null);
      reload();
    }
  }

  async function toggleActive(integration: Integration) {
    try {
      await api(`/api/v1/integrations/${integration.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ isActive: !integration.isActive }),
      });
    } finally {
      reload();
    }
  }

  const isConnections = kind === "MESSENGER";
  const rowHandlers = {
    testingId,
    onTest: test,
    onEdit,
    onToggleActive: toggleActive,
    onDelete: (item: Integration) => setDeleting(item),
  };

  return (
    <div className="integrations-section">
      {items.length === 0 ? (
        <EmptyState title={isConnections ? t("settings.no_connections_yet_add_bot") : t("settings.no_providers_yet_add_openrouter")} />
      ) : isConnections ? (
        <ConnectionsTable items={items} {...rowHandlers} />
      ) : (
        <ProvidersTable items={items} {...rowHandlers} />
      )}
      {deleting && <DeleteIntegrationDialog integration={deleting} onClose={() => setDeleting(null)} onDeleted={() => { setDeleting(null); reload(); }} />}
    </div>
  );
}
