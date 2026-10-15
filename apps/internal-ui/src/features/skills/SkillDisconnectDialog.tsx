import { Modal } from "antd";
import { useState } from "react";
import { t } from "../../i18n";
import { Button } from "../../shared/ui-controls";
import { assignSkill, getSkill, isConflict, skillError, type Skill } from "./model";
export function SkillDisconnectDialog({
  initial,
  agentId,
  name,
  close,
  changed,
}: {
  initial: Skill;
  agentId: number;
  name: string;
  close: () => void;
  changed: () => void;
}) {
  const [skill, setSkill] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [refresh, setRefresh] = useState(false);
  async function disconnect() {
    setBusy(true);
    setError("");
    try {
      await assignSkill(skill, agentId, false);
      changed();
      close();
    } catch (caught) {
      setError(skillError(caught));
      setConflict(isConflict(caught));
    } finally {
      setBusy(false);
    }
  }
  async function reload() {
    setBusy(true);
    try {
      setSkill((await getSkill(skill.id)).skill);
      setConflict(false);
      setError("");
    } catch (caught) {
      setError(skillError(caught));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      open
      width={460}
      title={t("skills.disconnect_title", { name: skill.name })}
      onCancel={() => {
        if (!busy) close();
      }}
      footer={
        <div className="skill-actions">
          <Button variant="secondary" disabled={busy} onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button variant="primary" disabled={busy || conflict} onClick={() => void disconnect()}>
            {t("skills.disconnect")}
          </Button>
        </div>
      }>
      <p>{t("skills.disconnect_hint", { name })}</p>
      {error && (
        <div className="skill-notice is-error" role="alert">
          {error}
          {conflict && (
            <Button variant="secondary" disabled={busy} onClick={() => setRefresh(true)}>
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
          void reload();
        }}
      />
    </Modal>
  );
}
