import type { ReactNode } from "react";
import { Icon } from "../../shared/icons";

export function QualityBanner({ tone, title, text, actions }: { tone: "info" | "error" | "warning"; title: string; text: string; actions?: ReactNode }) {
  return <div className={`quality-banner is-${tone}`} role={tone === "info" ? "status" : "alert"}>
    <Icon name={tone === "error" ? "errorCircle" : tone === "warning" ? "warning" : "info"} size={16} />
    <span className="quality-banner-text"><b>{title}</b> {text}</span>
    {actions && <span className="quality-banner-actions">{actions}</span>}
  </div>;
}
