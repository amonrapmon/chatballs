import { Icon } from "./icons";

export type SectionMenuItem<Key extends string> = {
  key: Key;
  label: string;
  icon: Parameters<typeof Icon>[0]["name"];
  hint?: { text: string; tone?: "ok" | "muted" };
  divider?: boolean;
  danger?: boolean;
  disabled?: boolean;
};

export function SectionMenu<Key extends string>({ items, activeKey, note, onSelect }: {
  items: readonly SectionMenuItem<Key>[];
  activeKey: Key;
  note?: string;
  onSelect: (key: Key) => void;
}) {
  return (
    <nav className="section-menu">
      {items.map((item) => (
        <span key={item.key}>
          <button
            className={`section-menu-item${item.key === activeKey ? " is-active" : ""}${item.danger ? " is-danger" : ""}`}
            type="button"
            disabled={item.disabled}
            onClick={() => onSelect(item.key)}
          >
            <Icon name={item.icon} size={16} strokeWidth={1.9} />
            <span>{item.label}</span>
            {item.hint && <small className={item.hint.tone === "ok" ? "is-ok" : ""}>{item.hint.text}</small>}
          </button>
          {item.divider && <i className="section-menu-divider" />}
        </span>
      ))}
      {note && <><span className="section-menu-gap" /><p>{note}</p></>}
    </nav>
  );
}
