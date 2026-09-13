import { useCallback, useEffect, useState } from "react";

import {
  browserAndOs,
  browserNotificationState,
  requestBrowserNotifications,
  type BrowserNotificationState,
} from "../notifications/browserNotifications";
import { fetchPreference, savePreference, type NotificationPreference } from "../notifications/model";
import { Icon, LogoSpinner } from "../../shared/icons";
import { Button } from "../../shared/ui-controls";
import { t } from "../../i18n";
import { NotificationTypeChecks } from "./NotificationTypeChecks";

// Строка «Этот браузер» в карточке уведомлений (макет «Очередь и уведомления»,
// кадры Q1 и Q1b) — того же вида, что строки ботов, и первой в списке: она
// включается одним нажатием и без внешнего аккаунта.
//
// Состояний три, и они не сводятся к «включено/выключено»: разрешение живёт в
// браузере и своё на каждом устройстве, а желание получать — на сервере.
// Отозвать выданное разрешение сайт не может, поэтому «Отключить» выключает
// именно желание; отказ снимается только руками в настройках браузера.

export function ProfileBrowserNotificationsRow() {
  // Состояние разрешения известно сразу: если узнавать его в эффекте, строка
  // на первый кадр возвращает null и мигает на каждой перерисовке страницы.
  const [permission, setPermission] = useState<BrowserNotificationState>(browserNotificationState);
  const [preference, setPreference] = useState<NotificationPreference | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchPreference("BROWSER").then(setPreference).catch(() => undefined);
  }, []);

  const apply = useCallback(async (patch: { enabled?: boolean; types?: string[] }) => {
    setBusy(true);
    try {
      setPreference(await savePreference("BROWSER", patch));
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  }, []);

  async function enable() {
    // Разрешение спрашиваем ровно здесь — в ответ на клик: на загрузке страницы
    // браузеры такой запрос наказывают, а отказ потом почти не отменить.
    const granted = await requestBrowserNotifications();
    setPermission(granted);
    if (granted === "granted") await apply({ enabled: true });
  }

  function toggleType(code: string) {
    if (!preference) return;
    const next = preference.types.includes(code)
      ? preference.types.filter((item) => item !== code)
      : [...preference.types, code];
    setPreference({ ...preference, types: next });
    void apply({ types: next });
  }

  if (permission === "unsupported") return null;

  const denied = permission === "denied";
  const on = permission === "granted" && Boolean(preference?.enabled);
  const device = browserAndOs();
  const tile = denied
    ? "integration-tile--blocked"
    : on
      ? "integration-tile--web"
      : "integration-tile--muted";
  return (
    <div className="profile-notifications-block">
      <div className="profile-notifications-row">
        <span className={`profile-notifications-tile integration-tile ${tile}`}>
          <Icon name={denied ? "bellOff" : "bell"} size={19} />
        </span>
        <div className="profile-notifications-name">
          <strong>{t("profile.this_browser")}</strong>
          <small>
            {denied
              ? device
              : on
                ? t("profile.browser_visible_when_minimized", { device })
                : t("profile.browser_not_enabled_yet")}
          </small>
        </div>
        {denied ? (
          <b className="profile-notifications-status is-blocked">
            <Icon name="xCircle" size={11} strokeWidth={2.4} />
            {t("profile.browser_blocked")}
          </b>
        ) : !preference ? (
          <span className="profile-notifications-wait"><LogoSpinner size={16} /></span>
        ) : on ? (
          <>
            <b className="profile-notifications-status">
              <Icon name="check" size={11} strokeWidth={2.6} />
              {t("profile.browser_enabled")}
            </b>
            <Button variant="secondary" disabled={busy} onClick={() => void apply({ enabled: false })}>
              {t("profile.disconnect")}
            </Button>
          </>
        ) : (
          <Button variant="primary" disabled={busy} onClick={() => void enable()}>{t("profile.enable")}</Button>
        )}
      </div>
      {on && preference && (
        <>
          <NotificationTypeChecks
            options={preference.availableTypes ?? []}
            selected={preference.types ?? []}
            onToggle={toggleType}
          />
          <p className="profile-notifications-aside">{t("profile.browser_disable_note")}</p>
        </>
      )}
      {denied && (
        <div className="profile-notifications-hint">
          <span><Icon name="lock" size={15} /></span>
          <div>
            <strong>{t("profile.browser_blocked_title")}</strong>
            <p>{t("profile.browser_blocked_steps")}</p>
            {/* Разрешение меняют в браузере; приложению остаётся перечитать его. */}
            <Button variant="secondary" onClick={() => setPermission(browserNotificationState())}>
              {t("profile.check_again")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
