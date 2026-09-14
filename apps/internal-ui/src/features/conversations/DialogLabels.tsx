import { Dropdown } from "antd";
import { useEffect, useState } from "react";
import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { createConversationLabel, fetchConversationLabels, setConversationLabels,
  type ApiConversation, type ConversationLabelRef } from "./model";
import "./dialogLabels.css";

export function DialogLabels({ detail, busy, setBusy, setErrorText, applyConversation, run }: {
  detail: ApiConversation;
  busy: boolean;
  setBusy: (busy: boolean) => void;
  setErrorText: (error: string) => void;
  applyConversation: (updated: ApiConversation) => void;
  run: (action: () => Promise<ApiConversation>) => Promise<void>;
}) {
  const [labels, setLabels] = useState<ConversationLabelRef[]>([]);
  const [newLabel, setNewLabel] = useState("");
  useEffect(() => { setNewLabel(""); }, [detail.id]);
  useEffect(() => {
    fetchConversationLabels().then(setLabels).catch((error) => {
      setErrorText(error instanceof Error ? error.message : t("conversations.could_not_add_label"));
    });
  }, [setErrorText]);

  async function addLabel(id?: number) {
    if (busy) return;
    let labelId = id;
    setBusy(true);
    setErrorText("");
    try {
      if (labelId === undefined) {
        const name = newLabel.trim();
        if (!name) return;
        const label = await createConversationLabel(name);
        setLabels((current) => (current.some((item) => item.id === label.id) ? current : [...current, label]));
        labelId = label.id;
        setNewLabel("");
      }
      const ids = [...new Set([...detail.labels.map((item) => item.id), labelId])];
      applyConversation(await setConversationLabels(detail.id, ids));
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("conversations.could_not_add_label"));
    } finally {
      setBusy(false);
    }
  }

  const assignedIds = new Set(detail.labels.map((item) => item.id));
  const availableLabels = labels.filter((item) => !assignedIds.has(item.id));
  return (
    <>
      <label className="ctx-label">{t("conversations.labels")}</label>
      <div className="ctx-labels">
        <Dropdown
          disabled={busy}
          trigger={["click"]}
          overlayClassName="app-dropdown is-wide ctx-labels-menu"
          menu={{
            items: [
              ...availableLabels.map((label) => ({
                key: label.id,
                label: <button type="button" onClick={() => void addLabel(label.id)}><i className="ctx-dot is-square" style={{ background: label.color || "var(--n-5)" }} />{label.name}</button>,
              })),
              {
                key: "new",
                label: (
                  <div className="ctx-new-label" onClick={(event) => event.stopPropagation()}>
                    <input
                      aria-label={t("conversations.new_label")}
                      disabled={busy}
                      placeholder={t("conversations.new_label")}
                      value={newLabel}
                      onChange={(event) => setNewLabel(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.stopPropagation();
                          event.preventDefault();
                          void addLabel();
                        }
                      }}
                    />
                    <button type="button" aria-label={t("conversations.add")} disabled={busy || !newLabel.trim()} onClick={() => void addLabel()}><Icon name="plus" size={13} /></button>
                  </div>
                ),
              },
            ],
          }}
        >
          <button type="button" className="ctx-add-label"><Icon name="plus" size={13} />{t("conversations.add")}</button>
        </Dropdown>
        {detail.labels.map((label) => (
          <b className="ctx-label-chip" key={label.id}>
            <i style={{ background: label.color || "var(--n-5)" }} />
            {label.name}
            <button
              aria-label={t("conversations.remove_label", { name: label.name })}
              disabled={busy}
              type="button"
              onClick={() => void run(() => setConversationLabels(detail.id, detail.labels.filter((item) => item.id !== label.id).map((item) => item.id)))}
            >
              ×
            </button>
          </b>
        ))}
      </div>

    </>
  );
}
