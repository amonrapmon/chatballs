import { Modal } from "antd";
import { useState } from "react";
import { t } from "../../i18n";
import { FormField, SelectField } from "../../shared/form-controls";
import { Button } from "../../shared/ui-controls";
import type { EmployeeGroup } from "../../types";
import { createAgent } from "./model";

/** Мастер одного шага (SPEC-CHATBALLS-0031 §4.3, кадр G2): имя и группа. */
export function CreateAgentModal({
  groups,
  onClose,
  onCreated,
}: {
  groups: EmployeeGroup[];
  onClose: () => void;
  onCreated: (agentId: number) => void;
}) {
  const [name, setName] = useState("");
  const [groupId, setGroupId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await createAgent({ name: name.trim(), groupId });
      onCreated(created.agent.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("ai.could_not_create_agent"));
      setSubmitting(false);
    }
  }

  return (
    <Modal
      className="agent-create-modal"
      open
      width={440}
      title={t("profile.create_agent")}
      onCancel={onClose}
      footer={null}
      destroyOnClose>
      <p className="agent-create-lead">{t("ai.one_step_instructions_model_knowledge")}</p>
      <div className="agent-create-fields">
        <FormField label={t("common.title")} value={name} onChange={setName} placeholder={t("ai.example_front_desk")} />
        <SelectField
          label={t("common.group")}
          value={groupId === null ? "" : String(groupId)}
          onChange={(value) => setGroupId(value ? Number(value) : null)}
          options={[
            ["", t("ai.without_group_conversations_visible_everyone")],
            ...groups.map((item) => [String(item.id), item.name] as [string, string]),
          ]}
        />
        {error && <div className="agent-form-error">{error}</div>}
      </div>
      <div className="agent-create-actions">
        <Button variant="secondary" onClick={onClose}>
          {t("common.cancel")}
        </Button>
        <Button variant="primary" disabled={!name.trim() || submitting} onClick={() => void submit()}>
          {submitting ? t("ai.creating") : t("ai.create_2")}
        </Button>
      </div>
    </Modal>
  );
}
