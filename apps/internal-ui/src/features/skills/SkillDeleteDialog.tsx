import { Modal } from "antd";
import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { t, tn } from "../../i18n";
import { Button } from "../../shared/ui-controls";
import { EmptyState, ErrorScreen, LoadingState, PermissionScreen } from "../../shared/ui";
import { deleteSkill, getDeletion, isConflict, skillError, type Skill } from "./model";
import { Icon } from "../../shared/icons";
export function SkillDeleteDialog({ id, close, deleted }: { id: string; close: () => void; deleted: () => void }) {
  const [skill, setSkill] = useState<Skill | null>(null);
  const [failure, setFailure] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [refresh, setRefresh] = useState(false);
  async function load() {
    setFailure(0);
    setSkill(null);
    try {
      setSkill((await getDeletion(id)).skill);
      setConflict(false);
      setError("");
    } catch (caught) {
      setFailure(caught instanceof ApiError ? caught.status : 500);
    }
  }
  useEffect(() => {
    void load();
  }, [id]);
  async function remove() {
    if (!skill || busy) return;
    setBusy(true);
    setError("");
    try {
      await deleteSkill(skill);
      deleted();
    } catch (caught) {
      setError(skillError(caught));
      setConflict(isConflict(caught));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      open
      width={480}
      title={t("skills.delete_title", { name: skill?.name ?? "" })}
      onCancel={() => {
        if (!busy) close();
      }}
      footer={
        skill ? (
          <div className="skill-actions">
            <Button variant="secondary" disabled={busy} onClick={close}>
              {t("common.cancel")}
            </Button>
            <Button variant="danger-outline" disabled={busy || conflict} onClick={() => void remove()}>
              {t("skills.delete_action")}
            </Button>
          </div>
        ) : null
      }>
      {failure === 403 ? (
        <PermissionScreen onReturn={close} />
      ) : failure === 404 ? (
        <EmptyState title={t("skills.not_found")} />
      ) : failure ? (
        <ErrorScreen retry={() => void load()} />
      ) : !skill ? (
        <LoadingState />
      ) : (
        <>
          <p>{t("skills.delete_hint")}</p>
          <p>{tn("skills.delete_agents", skill.agentCount)}</p>
          {skill.agents.map((agent) => (
            <div className="skill-agent" key={agent.id}>
              <Icon name="robot" size={16} />
              <strong>{agent.name}</strong>
            </div>
          ))}
          <p>
            {tn("skills.template_count", skill.templateCount)}
            {skill.templates.length > 0 && `: ${skill.templates.map((item) => item.name).join(", ")}`}
          </p>
          <div className="skill-notice is-warning">
            <Icon name="warning" size={14} />
            <span>{t("skills.bounds_history")}</span>
          </div>
        </>
      )}
      {error && (
        <div className="skill-notice is-error" role="alert">
          {error}
          {conflict && (
            <Button variant="secondary" onClick={() => setRefresh(true)}>
              {t("skills.refresh")}
            </Button>
          )}
        </div>
      )}
      <Modal
        open={refresh}
        title={t("skills.replace")}
        okText={t("skills.replace_action")}
        cancelText={t("common.cancel")}
        onCancel={() => setRefresh(false)}
        onOk={() => {
          setRefresh(false);
          void load();
        }}
      />
    </Modal>
  );
}
