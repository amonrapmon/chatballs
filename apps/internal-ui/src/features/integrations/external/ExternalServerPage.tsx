import { useState } from "react";
import { fmt, t } from "../../../i18n";
import { SectionMenu, type SectionMenuItem } from "../../../shared/SectionMenu";
import type { Integration } from "../model";
import { DeleteIntegrationDialog } from "../DeleteIntegrationDialog";
import { HttpParameters } from "./HttpParameters";
import { HttpToolForm } from "./HttpToolForm";
import { McpTools } from "./McpTools";
import { ServerConnection } from "./ServerConnection";
import { ServerHeader } from "./ServerHeader";
import { useServerEditor } from "./useServerEditor";
import type { ServerKind } from "./types";
import "../../support-portals/styles-detail.css";
import "../../support-portals/styles-settings.css";
import "../web-integration.css";
import "./styles.css";
import "./tools.css";
import "./parameters.css";

type Section = "main" | "tools" | "parameters" | "delete";

export function ExternalServerPage({ initial, kind, integrations, onCreated, onBack, onOpenSettings }: {
  initial: Integration | null; kind: ServerKind; integrations: Integration[];
  onCreated: (id: number) => void; onBack: () => void; onOpenSettings: () => void;
}) {
  const editor = useServerEditor(kind, initial, onCreated);
  const [section, setSection] = useState<Section>("main");
  const [deleting, setDeleting] = useState(false);
  const mcp = kind === "mcp";
  const items: SectionMenuItem<Section>[] = [
    { key: "main", label: t(mcp ? "servers.connection" : "servers.tool"), icon: mcp ? "plug" : "wrench" },
    mcp ? { key: "tools", label: t("ai.tools"), icon: "wrench", hint: { text: fmt.number(editor.integration?.externalServer?.tools?.length ?? 0) } }
      : { key: "parameters", label: t("servers.parameters"), icon: "list", hint: { text: fmt.number(editor.draft.externalServer.parameters?.length ?? 0) } },
    { key: "delete", label: t("servers.delete"), icon: "trash", danger: true, disabled: !editor.integration, divider: true },
  ];
  return <section className="web-integration-page external-server-page">
    <ServerHeader editor={editor} onBack={onBack} onOpenSettings={onOpenSettings} />
    <div className="portal-settings-layout">
      <SectionMenu items={items} activeKey={section} note={t("servers.changes_note")}
        onSelect={(key) => key === "delete" ? setDeleting(true) : setSection(key)} />
      <div className="portal-settings-content">
        {section === "main" && (mcp ? <ServerConnection editor={editor} /> : <HttpToolForm editor={editor} />)}
        {section === "tools" && <McpTools editor={editor} openConnection={() => setSection("main")} />}
        {section === "parameters" && <HttpParameters editor={editor} integrations={integrations} />}
      </div>
    </div>
    {deleting && editor.integration && <DeleteIntegrationDialog integration={editor.integration} onClose={() => setDeleting(false)} onDeleted={onBack} />}
  </section>;
}
