import { useRef, useState } from "react";

import { apiUpload } from "../../../api/client";
import { t, type MessageKey } from "../../../i18n";
import { Icon } from "../../../shared/icons";
import { headerIconRow, launcherIconRow, SHAPE_RADIUS, type IconRow, type WidgetAppearance } from "./model";
import { WidgetIcon } from "./WidgetIcon";

/** `onChange`: адрес загруженного файла, `""` — сбросить, `null` — без иконки. */
function IconUpload({ integrationId, label, row, radius, onChange, onBusy }: {
  integrationId: number; label: MessageKey; row: IconRow; radius: string;
  onChange: (url: string | null) => void; onBusy: (busy: boolean) => void;
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
      onChange(url);
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
      <span className={`widget-icon-tile${row.url === null ? " is-none" : ""}`} style={{ borderRadius: radius }}>
        {row.url === null
          ? <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="12" r="8" /><path d="M6.5 17.5l11-11" /></svg>
          : <WidgetIcon url={row.url} size={26} />}
      </span>
      <span className="widget-icon-caption"><strong>{t(row.caption)}</strong><small>{t(row.note)}</small></span>
      <span className="widget-icon-actions">
        <button type="button" className="portal-inline-button" disabled={busy} aria-label={`${t("widget_appearance.upload")}: ${t(label)}`} onClick={() => input.current?.click()}>
          <Icon name="upload" size={13} />{t("widget_appearance.upload")}
        </button>
        {row.canRemove && <button type="button" className="link is-muted" disabled={busy} aria-label={`${t("widget_appearance.no_icon")}: ${t(label)}`} onClick={() => onChange(null)}>{t("widget_appearance.no_icon")}</button>}
        {row.canReset && <button type="button" className="link is-muted" disabled={busy} aria-label={`${t("widget_appearance.reset")}: ${t(label)}`} onClick={() => onChange("")}>{t("widget_appearance.reset")}</button>}
      </span>
      <input hidden ref={input} type="file" accept="image/svg+xml,image/png,.svg,.png" aria-label={t(label)}
        onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); }} />
    </div>
    <small className="widget-appearance-hint">{t(row.hint)}</small>
    {error && <small className="integration-form-error" role="alert">{error}</small>}
  </div>;
}

export function IconSettings({ integrationId, appearance, onChange, onBusy }: {
  integrationId: number; appearance: WidgetAppearance;
  onChange: (patch: Partial<WidgetAppearance>) => void; onBusy: (key: string, busy: boolean) => void;
}) {
  return <div className="widget-appearance-card widget-icon-settings">
    <IconUpload integrationId={integrationId} label="widget_appearance.launcher_icon" row={launcherIconRow(appearance)}
      radius={SHAPE_RADIUS[appearance.launcherShape]}
      onChange={(launcherIcon) => onChange({ launcherIcon: launcherIcon ?? "" })} onBusy={(busy) => onBusy("launcher", busy)} />
    <IconUpload integrationId={integrationId} label="widget_appearance.header_icon" row={headerIconRow(appearance)}
      radius="10px"
      onChange={(headerIcon) => onChange({ headerIcon })} onBusy={(busy) => onBusy("header", busy)} />
  </div>;
}
