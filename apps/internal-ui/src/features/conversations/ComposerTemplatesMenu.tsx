import type { ReplyTemplateRef } from "./model";
import { t } from "../../i18n";

export function ComposerTemplatesMenu({ items, onPick }: { items: ReplyTemplateRef[]; onPick: (template: ReplyTemplateRef) => void }) {
  return (
    <div className="composer-templates-menu">
      {items.length === 0 && <p>{t("conversations.no_matching_templates")}</p>}
      {items.map((template) => (
        <button key={template.id} type="button" onMouseDown={(event) => { event.preventDefault(); onPick(template); }}>
          <strong>{template.title}</strong>
          <small>{template.text.replace(/\s+/g, " ").slice(0, 80)}</small>
        </button>
      ))}
    </div>
  );
}
