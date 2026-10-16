import { Dropdown, Modal } from "antd";
import { useState } from "react";
import { t } from "../../../i18n";
import { FormField, TextAreaField } from "../../../shared/form-controls";
import { Button } from "../../../shared/ui-controls";
import { Icon } from "../../../shared/icons";
import type { SkillTemplate } from "../model";
import { FieldDialog } from "./FieldDialog";
import { pathLabel, removeField, schemaRows, type SchemaNode } from "./schema";
import type { Diagnostic } from "./api";

export function TemplateFields({ template, change, errors, disabled, touch }: {
  template: SkillTemplate; change: (next: SkillTemplate) => void; errors: Diagnostic[]; disabled: boolean; touch: (path: string) => void;
}) {
  const [editing, setEditing] = useState<{ path?: string } | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const schema = template.schema as SchemaNode;
  const changeSchema = (next: SchemaNode) => change({ ...template, schema: next });
  const errorFor = (path: string) => errors.filter((error) => error.tab === "schema" && error.path === path);
  return <section className="template-fields template-panel">
    <FormField label={t("skills.name")} value={template.name} disabled={disabled}
      error={errorFor("name")[0]?.detail}
      onBlur={() => touch("name")}
      onChange={(name) => change({ ...template, name })} />
    <div className={errorFor("purpose").length ? "is-invalid" : ""} onBlur={() => touch("purpose")}>
      <TextAreaField label={t("skill_templates.purpose")} value={template.purpose} disabled={disabled}
        onChange={(purpose) => change({ ...template, purpose })} />
      <small>{t("skill_templates.purpose_hint")}</small>
      {errorFor("purpose").map((error, i) => <small className="template-error" key={i}>{error.detail}</small>)}
    </div>
    <header><strong>{t("skill_templates.fields")}</strong>
      <Button variant="secondary" icon="plus" disabled={disabled} onClick={() => setEditing({})}>{t("skill_templates.field")}</Button></header>
    <div className="template-schema-list">{schemaRows(schema).map(({ path, name, node, depth }) => {
      const fieldErrors = errors.filter((error) => ["schema", "example"].includes(error.tab)
        && error.path.replace(/\[\d+\]/g, "[]") === pathLabel(path));
      return <div key={path} className={`template-schema-field ${fieldErrors.length ? "is-invalid" : ""}`}
        style={{ marginLeft: depth * 14 }}>
        <div><code>{name}</code><span>{t(`skill_templates.${node.type}`)}</span>
          <small className={node.required ? "is-required" : ""}>{t(node.required ? "skill_templates.required_short" : "skill_templates.optional")}</small>
          <Dropdown trigger={["click"]} overlayClassName="app-dropdown" menu={{ items: [
            { key: "edit", label: t("common.edit"), onClick: () => setEditing({ path }) },
            { key: "delete", label: t("common.delete"), danger: true, onClick: () => {
              if (node.type === "object" || node.type === "list") setDeleting(path);
              else changeSchema(removeField(schema, path));
            } },
          ] }}><button className="row-menu-button" disabled={disabled} aria-label={`${name}: ${t("common.actions")}`}><Icon name="more" size={14} /></button></Dropdown>
        </div>
        {node.description && <small>{node.description}</small>}
        {fieldErrors.map((error, i) => <small className="template-error" key={i}>{error.detail}</small>)}
      </div>;
    })}</div>
    {editing && <FieldDialog schema={schema} editing={editing.path} change={changeSchema} close={() => setEditing(null)} />}
    <Modal open={deleting !== null} title={t("skill_templates.delete_field", { name: pathLabel(deleting ?? "") })}
      onCancel={() => setDeleting(null)} okText={t("common.delete")} cancelText={t("common.cancel")} okButtonProps={{ danger: true }}
      onOk={() => { if (deleting) changeSchema(removeField(schema, deleting)); setDeleting(null); }}>
      <p>{t("skill_templates.delete_children")}</p>
    </Modal>
  </section>;
}
