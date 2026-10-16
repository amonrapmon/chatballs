import { t, tn } from "../../i18n";
import type { SkillTemplate } from "./model";
export function SkillTemplateMeta({ template }: { template: SkillTemplate }) {
  const properties = template.schema.properties as Record<string, { required?: boolean; type?: string }> | undefined;
  const fields = Object.values(properties ?? {});
  const optional = fields.filter((field) => !field.required).length;
  return (
    <div className="skill-chips">
      <span className="skill-chip">
        {tn("skills.field_count", fields.length)}
        {fields.some((field) => field.type === "list")
          ? ` · ${t("skills.field_list")}`
          : optional
            ? ` · ${tn("skills.optional_count", optional)}`
            : ""}
      </span>
      {(template.html || template.css) && <span className="skill-chip">{t("skills.html_css")}</span>}
      <span className="skill-chip">{t("skills.text_version")}</span>
    </div>
  );
}
