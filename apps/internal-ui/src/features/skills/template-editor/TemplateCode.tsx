import { useState } from "react";
import { t, fmt } from "../../../i18n";
import { Icon } from "../../../shared/icons";
import type { SkillTemplate } from "../model";
import type { Diagnostic } from "./api";
import { CodeEditor } from "./CodeEditor";

export function TemplateCode({ template, change, errors, disabled, updatedAt }: {
  template: SkillTemplate; change: (next: SkillTemplate) => void; errors: Diagnostic[]; disabled: boolean;
  updatedAt?: string;
}) {
  const [tab, setTab] = useState<"html" | "css" | "text">("html");
  return <section className="template-panel template-code">
    <div className="template-code-tabs" role="tablist">
      {(["html", "css", "text"] as const).map((key) => {
        const count = errors.filter((error) => error.tab === key).length;
        return <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "is-active" : ""}
          onClick={() => setTab(key)}>{t(`skill_templates.${key}`)}{count > 0 && <b>{count}</b>}</button>;
      })}
      {updatedAt && <small className="template-code-updated">{t("skills.updated")} {fmt.shortDate(updatedAt)}</small>}
    </div>
    <CodeEditor key={tab} value={template[tab]} language={tab} label={t("skill_templates.code") + ": " + t(`skill_templates.${tab}`)}
      change={(value) => change({ ...template, [tab]: value })} errors={errors.filter((error) => error.tab === tab)} disabled={disabled} />
    <footer className="template-syntax">
      <span><code>{t("skill_templates.value_syntax")}</code>{t("skill_templates.substitution")}</span>
      <span><code>{t("skill_templates.each_syntax")}</code>{t("skill_templates.loop")}</span>
      <span><code>{t("skill_templates.if_syntax")}</code>{t("skill_templates.condition")}</span>
      <span><Icon name="shield" size={12} />{t("skill_templates.scriptless")}</span>
    </footer>
  </section>;
}
