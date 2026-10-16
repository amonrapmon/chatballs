import { Dropdown } from "antd";
import { t } from "../../i18n";
import { Button } from "../../shared/ui-controls";
import { Icon } from "../../shared/icons";
import type { SkillTemplate } from "./model";
import { SkillTemplateMeta } from "./SkillTemplateMeta";

export function SkillTemplates({
  templates,
  open,
  remove,
}: {
  templates: SkillTemplate[];
  open?: (id: string | null) => void;
  remove: (id: string) => void;
}) {
  return (
    <section className="skill-panel">
      <header className="skill-section-head">
        <div>
          <h3>{t("skills.templates")}</h3>
          <p>{t("skills.templates_hint")}</p>
        </div>
        <Button
          variant="secondary"
          icon="plus"
          disabled={!open}
          title={!open ? t("skills.template_unavailable") : undefined}
          onClick={() => open?.(null)}>
          {t("skills.add_template")}
        </Button>
      </header>
      {templates.map((template) => (
        <div className="skill-template" key={template.id}>
          <span className="skill-tile">
            <Icon name="columns" size={17} />
          </span>
          <div>
            <strong>{template.name}</strong>
            <small>{template.purpose}</small>
            <SkillTemplateMeta template={template} />
          </div>
          <Button
            variant="secondary"
            disabled={!open}
            title={!open ? t("skills.template_unavailable") : undefined}
            onClick={() => open?.(template.id)}>
            {t("common.edit")}
          </Button>
          <Dropdown
            trigger={["click"]}
            overlayClassName="app-dropdown"
            menu={{
              items: [{ key: "delete", label: t("common.delete"), danger: true, onClick: () => remove(template.id) }],
            }}>
            <button className="row-menu-button" aria-label={t("common.actions")}>
              <Icon name="more" size={16} />
            </button>
          </Dropdown>
        </div>
      ))}
      {!templates.length && (
        <div className="skill-no-templates">
          <span className="skill-tile">
            <Icon name="text" size={16} />
          </span>
          <div>
            <strong>{t("skills.ordinary")}</strong>
            <small>{t("skills.ordinary_hint")}</small>
          </div>
        </div>
      )}
    </section>
  );
}
