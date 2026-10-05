import { useRef, useState } from "react";

import { apiUpload } from "../../../api/client";
import { t, type MessageKey } from "../../../i18n";
import { Icon } from "../../../shared/icons";
import { SHAPE_RADIUS, type WidgetAppearance } from "./model";
import { WidgetIcon } from "./WidgetIcon";

function IconUpload({ integrationId, label, hint, url, radius, onUploaded, onBusy }: {
  integrationId: number; label: MessageKey; hint: MessageKey; url: string | null; radius: string;
  onUploaded: (url: string) => void; onBusy: (busy: boolean) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function upload(file: File) {
    setBusy(true);
    onBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const { url } = await apiUpload<{ url: string }>(`/api/v1/integrations/${integrationId}/assets/`, form);
      onUploaded(url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("common.request_failed"));
    } finally {
      setBusy(false);
      onBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return <div>
    <span className="widget-appearance-label">{t(label)}</span>
    <div className="widget-icon-upload">
      <span className="widget-icon-tile" style={{ borderRadius: radius }}><WidgetIcon url={url} size={26} /></span>
      <span className="widget-icon-caption"><strong>{t("widget_appearance.agent_mark")}</strong><small>{t("widget_appearance.icon_requirements")}</small></span>
      <button type="button" className="portal-inline-button" disabled={busy} aria-label={`${t("widget_appearance.upload")}: ${t(label)}`} onClick={() => input.current?.click()}>
        <Icon name="upload" size={13} />{t("widget_appearance.upload")}
      </button>
      <input hidden ref={input} type="file" accept="image/svg+xml,image/png,.svg,.png" aria-label={t(label)}
        onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); }} />
    </div>
    <small className="widget-appearance-hint">{t(hint)}</small>
    {error && <small className="integration-form-error" role="alert">{error}</small>}
  </div>;
}

export function IconSettings({ integrationId, appearance, onChange, onBusy }: {
  integrationId: number; appearance: WidgetAppearance;
  onChange: (patch: Partial<WidgetAppearance>) => void; onBusy: (key: string, busy: boolean) => void;
}) {
  return <div className="widget-appearance-card widget-icon-settings">
    <IconUpload integrationId={integrationId} label="widget_appearance.launcher_icon" hint="widget_appearance.launcher_hint"
      url={appearance.launcherIcon} radius={SHAPE_RADIUS[appearance.launcherShape]}
      onUploaded={(launcherIcon) => onChange({ launcherIcon })} onBusy={(busy) => onBusy("launcher", busy)} />
    <IconUpload integrationId={integrationId} label="widget_appearance.header_icon" hint="widget_appearance.header_hint"
      url={appearance.headerIcon === "" ? appearance.launcherIcon : appearance.headerIcon} radius="10px"
      onUploaded={(headerIcon) => onChange({ headerIcon })} onBusy={(busy) => onBusy("header", busy)} />
  </div>;
}
