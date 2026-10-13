import { Dropdown } from "antd";
import { Icon } from "../../shared/icons";
import { t } from "../../i18n";
import { PriorityBars } from "./DialogList";
import type { ConversationPriority } from "./model";

const COLORS = { HIGH: "var(--error-text)", MEDIUM: "#d46b08", LOW: "var(--primary-text)", NONE: "var(--n-4)" };

export function DialogPriorityField({ priority, busy, onPick }: {
  priority: ConversationPriority;
  busy: boolean;
  onPick: (value: ConversationPriority) => void;
}) {
  const options: Array<[ConversationPriority, string]> = [
    ["HIGH", t("conversations.high")], ["MEDIUM", t("conversations.medium")],
    ["LOW", t("conversations.low")], ["NONE", t("conversations.not_set")],
  ];
  return <>
    <label className="ctx-label">{t("conversations.priority")}</label>
    <Dropdown disabled={busy} trigger={["click"]} overlayClassName="app-dropdown ctx-menu"
      menu={{ items: options.map(([value, label]) => ({
        key: value,
        label: <button type="button" className={priority === value ? "is-checked" : ""} onClick={() => onPick(value)}>
          <PriorityBars priority={value} placeholder /><span>{label}</span>{priority === value && <Icon name="check" size={15} />}
        </button>,
      })) }}>
      <button type="button" className="ctx-select">
        <PriorityBars priority={priority} placeholder />
        <span style={{ color: COLORS[priority], fontWeight: priority === "NONE" ? 500 : 600 }}>{options.find(([value]) => value === priority)?.[1]}</span>
        <Icon name="chevron" size={14} />
      </button>
    </Dropdown>
  </>;
}
