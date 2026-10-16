import { useState } from "react";

import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { LoadingState } from "../../shared/ui";
import { BackLink, Button } from "../../shared/ui-controls";
import type { ReplyTemplateRef } from "../conversations/model";
import { ReplyTemplateForm } from "./ReplyTemplateForm";
import { TemplateDeleteDialog } from "./TemplateDeleteDialog";
import { TemplateLibraryTable } from "./TemplateLibraryTable";
import { TemplateLibraryToolbar } from "./TemplateLibraryToolbar";
import { TemplateTaxonomy } from "./TemplateTaxonomy";
import { useTemplateLibrary } from "./useTemplateLibrary";
import "./styles.css";

// Кадры N3–N9: одна библиотека в «Настройках» и на странице из меню
// пользователя (`employee`) — у сотрудника нет доступа к настройкам.

export function ReplyTemplateLibrary({ employee = false, onBack, onChanged }: {
  employee?: boolean;
  onBack?: () => void;
  /** Состав библиотеки изменился: субменю «Настроек» пересчитывает число. */
  onChanged?: () => void;
}) {
  const library = useTemplateLibrary();
  const [form, setForm] = useState<{ item: ReplyTemplateRef | null } | null>(null);
  const [deleting, setDeleting] = useState<ReplyTemplateRef | null>(null);
  const [taxonomy, setTaxonomy] = useState(false);
  const changed = () => { library.reload(); onChanged?.(); };

  return (
    <div className={`template-library ${employee ? "is-employee" : ""}`.trim()}>
      {taxonomy
        ? <BackLink label={t("settings.reply_templates")} onClick={() => setTaxonomy(false)} />
        : employee && onBack && <BackLink label={t("templates.back_to_chat")} onClick={onBack} />}
      <header className="settings-head">
        <div>
          <h2>{t(taxonomy ? "templates.taxonomy" : "settings.reply_templates")}</h2>
          <p>{t(taxonomy ? "templates.taxonomy_lead" : employee ? "templates.employee_lead" : "templates.lead")}</p>
        </div>
        {!taxonomy && library.ready && (
          <Button variant="primary" icon="plus" onClick={() => setForm({ item: null })}>
            {t(library.canManageShared ? "settings.add_template" : "templates.add_personal")}
          </Button>
        )}
      </header>
      {!library.ready && !library.error && <LoadingState />}
      {library.ready && !taxonomy && library.scope === "SHARED" && !library.canManageShared && (
        <div className="template-readonly-banner">
          <Icon name="info" size={16} strokeWidth={1.9} />
          <span><b>{t("templates.readonly_title")}</b> {t("templates.readonly_help")}</span>
        </div>
      )}
      {(library.ready || library.error) && !taxonomy && (
        <div className="table-card template-library-card">
          <TemplateLibraryToolbar library={library} onTaxonomy={() => setTaxonomy(true)} />
          <TemplateLibraryTable library={library} onEdit={(item) => setForm({ item })} onDelete={setDeleting} />
        </div>
      )}
      {library.ready && taxonomy && <TemplateTaxonomy library={library} reload={changed} />}
      {form && (
        <ReplyTemplateForm
          initial={form.item}
          initialScope={library.canManageShared ? library.scope : "PERSONAL"}
          canManageShared={library.canManageShared}
          onClose={() => setForm(null)}
          onSaved={(scope) => {
            setForm(null);
            if (scope !== library.scope) library.setScope(scope);
            changed();
          }}
        />
      )}
      {deleting && <TemplateDeleteDialog item={deleting} onClose={() => setDeleting(null)} onDeleted={() => { setDeleting(null); changed(); }} />}
    </div>
  );
}
