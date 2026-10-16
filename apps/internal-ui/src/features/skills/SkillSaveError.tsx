import { t } from "../../i18n";
import { Button } from "../../shared/ui-controls";
import { Icon } from "../../shared/icons";
import type { useSkillDraft } from "./useSkillDraft";

export function SkillSaveError({ state, refresh, openTemplate }: {
  state: ReturnType<typeof useSkillDraft>; refresh: () => void; openTemplate?: (id: string) => void;
}) {
  if (!state.error) return null;
  return <div className="skill-notice is-error" role="alert">
    <Icon name="warning" size={16} /><span>{state.error}
      {openTemplate && state.validationErrors.map((error, index) => {
        const position = /^templates\[(\d+)\]/.exec(error.path);
        const template = position ? state.draft.templates[Number(position[1])] : undefined;
        return template && <div key={index}><button className="link is-neutral" onClick={() => openTemplate(template.id)}>
          {template.name || t("skill_templates.new")}: {error.detail}
        </button></div>;
      })}</span>
    <Button variant="secondary" disabled={state.busy} onClick={state.conflict ? refresh : () => void state.retry()}>
      {t(state.conflict ? "skills.refresh" : "common.try_again")}</Button>
  </div>;
}
