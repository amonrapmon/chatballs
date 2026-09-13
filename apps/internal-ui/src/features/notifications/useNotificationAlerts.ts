import { notification as antToast } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";

import { fetchPreference, type AppNotification, type NotificationPreference } from "./model";
import { showBrowserNotification } from "./browserNotifications";

// Оклик о новом уведомлении: тост внутри вкладки и системное уведомление, если
// человек смотрит в другое место.
//
// Раньше тост показывался по росту счётчика непрочитанных. Счётчик — плохой
// признак события: три уведомления между опросами давали один тост, а
// прочтение в соседней вкладке роняло счётчик и глушило следующий. Считаем по
// идентификаторам: что человеку ещё не показывали, то и показываем.

export function useNotificationAlerts({
  items,
  onOpen,
}: {
  items: AppNotification[];
  onOpen: (notification: AppNotification) => void;
}) {
  const [preference, setPreference] = useState<NotificationPreference | null>(null);
  const shown = useRef<Set<number> | null>(null);
  const onOpenRef = useRef(onOpen);
  onOpenRef.current = onOpen;
  const preferenceRef = useRef(preference);
  preferenceRef.current = preference;

  const reloadPreference = useCallback(async () => {
    try {
      setPreference(await fetchPreference("BROWSER"));
    } catch {
      /* без настройки системных уведомлений просто не будет */
    }
  }, []);

  useEffect(() => {
    void reloadPreference();
  }, [reloadPreference]);

  useEffect(() => {
    // Первая загрузка только запоминает: накопленное за ночь не вываливают
    // стопкой тостов в лицо тому, кто открыл приложение утром.
    if (shown.current === null) {
      shown.current = new Set(items.map((item) => item.id));
      return;
    }
    const seen = shown.current;
    const fresh = items.filter((item) => item.unread && !seen.has(item.id));
    for (const item of items) seen.add(item.id);
    if (fresh.length === 0) return;

    const newest = fresh[0];
    antToast.open({ message: newest.title, description: newest.body, placement: "bottomRight" });

    const allowed = preferenceRef.current;
    if (!allowed?.enabled) return;
    for (const item of fresh) {
      if (!allowed.types?.includes(item.type)) continue;
      showBrowserNotification(item, (opened) => onOpenRef.current(opened));
    }
  }, [items]);

  return { preference, reloadPreference };
}
