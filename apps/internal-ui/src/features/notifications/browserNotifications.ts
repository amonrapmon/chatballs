import type { AppNotification } from "./model";

// Системное уведомление браузера — то, что видно, когда вкладка свёрнута или
// закрыта другим окном. Работает без service worker и без Web Push: пока хоть
// одна вкладка приложения открыта, этого достаточно, а «браузер закрыт» в
// продукте закрывают боты в мессенджере. Web Push потребовал бы исходящего
// доступа установки к чужому push-сервису — на self-hosted это лишняя внешняя
// зависимость ради случая, который уже закрыт.

export type BrowserNotificationState = "unsupported" | "default" | "granted" | "denied";

export function browserNotificationState(): BrowserNotificationState {
  if (typeof window === "undefined" || !("Notification" in window)) return "unsupported";
  return Notification.permission as BrowserNotificationState;
}

/** Спрашивать разрешение можно только в ответ на действие человека: браузеры
 *  наказывают за запрос на загрузке, а отказ потом почти не отменить. */
export async function requestBrowserNotifications(): Promise<BrowserNotificationState> {
  if (browserNotificationState() === "unsupported") return "unsupported";
  try {
    return (await Notification.requestPermission()) as BrowserNotificationState;
  } catch {
    return browserNotificationState();
  }
}

/** Человек смотрит на приложение: системное уведомление было бы лишним, ему
 *  хватит тоста в самом интерфейсе. */
function userIsLooking(): boolean {
  return document.visibilityState === "visible" && document.hasFocus();
}

export function showBrowserNotification(
  notification: AppNotification,
  onOpen: (notification: AppNotification) => void,
): void {
  if (browserNotificationState() !== "granted" || userIsLooking()) return;
  try {
    const shown = new Notification(notification.title, {
      body: notification.body,
      // Одинаковый тег схлопывает уведомление во всех вкладках сразу: у
      // оператора их обычно несколько, и три одинаковых оклика об одном
      // диалоге — повод выключить уведомления совсем.
      tag: `chatballs-notification-${notification.id}`,
      renotify: false,
    } as NotificationOptions);
    shown.onclick = () => {
      window.focus();
      onOpen(notification);
      shown.close();
    };
  } catch {
    /* уведомление — вспомогательный путь: его сбой ничего не ломает */
  }
}

/** «Chrome · macOS» — чтобы человек понимал, о каком именно устройстве речь:
 *  разрешение своё в каждом браузере и на каждой машине. */
export function browserAndOs(): string {
  if (typeof navigator === "undefined") return "";
  const ua = navigator.userAgent;
  const browser = /Edg\//.test(ua)
    ? "Edge"
    : /OPR\//.test(ua)
      ? "Opera"
      : /YaBrowser/.test(ua)
        ? "Yandex"
        : /Chrome\//.test(ua)
          ? "Chrome"
          : /Firefox\//.test(ua)
            ? "Firefox"
            : /Safari\//.test(ua)
              ? "Safari"
              : "";
  const os = /Windows/.test(ua)
    ? "Windows"
    : /Mac OS X/.test(ua)
      ? "macOS"
      : /Android/.test(ua)
        ? "Android"
        : /iPhone|iPad/.test(ua)
          ? "iOS"
          : /Linux/.test(ua)
            ? "Linux"
            : "";
  return [browser, os].filter(Boolean).join(" · ");
}
