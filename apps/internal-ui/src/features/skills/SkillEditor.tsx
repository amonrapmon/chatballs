import { Modal } from "antd";
import { useState } from "react";
import { t, tn } from "../../i18n";
import { BackLink, Button } from "../../shared/ui-controls";
import { EmptyState, ErrorScreen, LoadingState, PermissionScreen } from "../../shared/ui";
import { SkillFields } from "./SkillFields";
import { SkillSidebar } from "./SkillSidebar";
import { SkillTemplates, type TemplateEditorBridge } from "./SkillTemplates";
import { useSkillDraft } from "./useSkillDraft";
import { useSkillLeaveGuard } from "./useSkillLeaveGuard";
import { SkillLeaveDialog } from "./SkillLeaveDialog";
import { SkillEditorHeader } from "./SkillEditorHeader";
import { Icon } from "../../shared/icons";

export function SkillEditor({
  id,
  back,
  openAgent,
  remove,
  templateEditor,
}: {
  id: string;
  back: () => void;
  openAgent: (id: number) => void;
  remove: (id: string) => void;
  templateEditor?: TemplateEditorBridge;
}) {
  const state = useSkillDraft(id);
  const {
    saved,
    draft,
    setDraft,
    dirty,
    loading,
    failure,
    busy,
    error,
    conflict,
    basis,
    attempted,
    save,
    retry,
    load,
    changeBasis,
    reset,
  } = state;
  const leave = useSkillLeaveGuard(dirty);
  const [template, setTemplate] = useState<{ id: string | null } | null>(null);
  const [replacing, setReplacing] = useState<(() => void) | null>(null);
  const confirmReplace = (action: () => void) => setReplacing(() => action);
  const saveLabel = !saved
    ? t("skills.create")
    : saved.agentCount
      ? tn("skills.save_for", saved.agentCount)
      : t("common.save");
  if (failure === "forbidden") return <PermissionScreen onReturn={back} />;
  if (failure === "missing")
    return (
      <div className="agents-page">
        <BackLink label={t("skills.title")} onClick={back} />
        <EmptyState title={t("skills.not_found")} />
      </div>
    );
  if (failure === "load") return <ErrorScreen retry={() => void load()} />;
  if (loading) return <LoadingState />;

  const footer = (
    <div className="skill-actions">
      <Button variant="secondary" disabled={busy} onClick={() => leave.request(back)}>
        {t("common.cancel")}
      </Button>
      <Button variant="primary" disabled={busy || conflict || (!dirty && !!saved)} onClick={() => void save()}>
        {saveLabel}
      </Button>
    </div>
  );
  return (
    <>
      {template && templateEditor ? (
        templateEditor({
          configuration: draft,
          templateId: template.id,
          change: setDraft,
          save,
          back: () => setTemplate(null),
        })
      ) : (
        <div className="skill-editor">
          <BackLink label={t("skills.title")} onClick={() => leave.request(back)} />
          <SkillEditorHeader skill={saved} busy={busy} remove={() => saved && remove(saved.id)} actions={footer} />
          {error && (
            <div className="skill-notice is-error" role="alert">
              <Icon name="warning" size={16} />
              <span>{error}</span>
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => (conflict ? confirmReplace(() => void load()) : void retry())}>
                {t(conflict ? "skills.refresh" : "common.try_again")}
              </Button>
            </div>
          )}
          <div className="skill-editor-grid">
            <div className="skill-column">
              <SkillFields
                draft={draft}
                change={setDraft}
                attempted={attempted}
                busy={busy}
                creating={!saved}
                basis={basis}
                changeBasis={(next) => {
                  if (dirty) confirmReplace(() => void changeBasis(next));
                  else void changeBasis(next);
                }}
              />
              <SkillTemplates
                templates={draft.templates}
                open={templateEditor ? (templateId) => setTemplate({ id: templateId }) : undefined}
                remove={(templateId) =>
                  setDraft({ ...draft, templates: draft.templates.filter((item) => item.id !== templateId) })
                }
              />
            </div>
            <SkillSidebar skill={saved} openAgent={(agentId) => leave.request(() => openAgent(agentId))} />
          </div>
          {dirty && (
            <div className="skill-save-bar">
              <i />
              <strong>{t("skills.unsaved")}</strong>
              <Button variant="secondary" disabled={busy} onClick={() => confirmReplace(reset)}>
                {t("skills.reset")}
              </Button>
              <Button variant="primary" disabled={busy || conflict} onClick={() => void save()}>
                {saveLabel}
              </Button>
            </div>
          )}
        </div>
      )}
      <Modal
        open={!!replacing}
        title={t("skills.replace")}
        onCancel={() => setReplacing(null)}
        okText={t("skills.replace_action")}
        cancelText={t("common.cancel")}
        onOk={() => {
          replacing?.();
          setReplacing(null);
        }}
      />
      <SkillLeaveDialog leave={leave} busy={busy} conflict={conflict} save={save} draft={draft} error={error} />
    </>
  );
}
