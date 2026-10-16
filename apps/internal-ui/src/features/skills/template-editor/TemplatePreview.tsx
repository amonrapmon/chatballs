import { useState } from "react";
import { PreparedMessage, type PreparedContent } from "@chatballs/ui";
import { t } from "../../../i18n";
import { Button } from "../../../shared/ui-controls";
import { Segmented } from "../../../shared/ui";
import type { Diagnostic } from "./api";

export function TemplatePreview({ content, errors, failure, retry }: {
  content?: PreparedContent; errors: Diagnostic[]; failure: string; retry: () => void;
}) {
  const [mode, setMode] = useState<"html" | "text">("html");
  const [width, setWidth] = useState<"340" | "300">("340");
  return <section className="template-panel template-preview">
    <header><strong>{t("skill_templates.preview")}</strong>
      <Segmented value={mode} setValue={setMode} items={[["html", t("skill_templates.widget")], ["text", t("skill_templates.text")]]} />
      <Segmented value={width} setValue={setWidth} items={[["340", "340"], ["300", "300"]]} />
    </header>
    <div className="template-preview-canvas">
      {(errors.length > 0 || failure) && <div className="template-preview-errors" role="alert">
        <strong>{t("skill_templates.unavailable")}</strong><p>{t("skill_templates.fix_errors")}</p>
        {errors.map((error, index) => <div key={index}>
          <span>{error.tab === "example" ? t("skill_templates.example") : error.tab === "schema" ? t("skill_templates.fields") : t(`skill_templates.${error.tab as "html"}`)}
            {error.line ? ` · ${t("skill_templates.line", { number: error.line })}` : ""}</span>
          <span>{(error.reference || error.path) && <code>{error.reference || error.path}: </code>}{error.detail}</span>
        </div>)}
        {failure && <><p>{failure}</p><Button variant="secondary" onClick={retry}>{t("common.try_again")}</Button></>}
      </div>}
      {content && !errors.length && !failure && <div className="template-preview-width" style={{ width: Number(width) }}>
        <small>{t("skill_templates.assistant")}</small>
        <div className={`template-preview-message ${mode === "text" ? "is-text" : ""}`}>
          <PreparedMessage content={content} mode={mode} title={t("skill_templates.preview")} />
        </div>
      </div>}
    </div>
  </section>;
}
