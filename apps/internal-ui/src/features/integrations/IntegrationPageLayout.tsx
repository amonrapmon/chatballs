import type { ReactNode } from "react";
import { SectionMenu, type SectionMenuItem } from "../../shared/SectionMenu";
import "../support-portals/styles-detail.css";
import "../support-portals/styles-settings.css";
import "./web-integration.css";

export function IntegrationPageLayout<Key extends string>({ header, items, activeKey, note, onSelect, children, className = "" }: {
  header: ReactNode;
  items: readonly SectionMenuItem<Key>[];
  activeKey: Key;
  note: string;
  onSelect: (key: Key) => void;
  children: ReactNode;
  className?: string;
}) {
  return <section className={`web-integration-page ${className}`.trim()}>
    {header}
    <div className="portal-settings-layout">
      <SectionMenu items={items} activeKey={activeKey} note={note} onSelect={onSelect} />
      <div className="portal-settings-content">{children}</div>
    </div>
  </section>;
}
