import { setCurrentLanguage } from "@chatballs/shared";
import { beforeEach, describe, expect, it } from "vitest";

import { latestStatus, presenceNote, statusChangedNote, statusLabel, statusSince, type WorkStatus } from "./model";

beforeEach(() => { setCurrentLanguage("ru"); });

describe("сохранённый статус", () => {
  const saved: WorkStatus = { status: "BREAK", version: 4, changedAt: "2026-10-10T13:30:00Z" };

  it("запоздавший ответ и повтор операции не затирают более свежий снимок", () => {
    const replay: WorkStatus = { status: "READY", version: 3, changedAt: "2026-10-10T09:12:00Z" };
    expect(latestStatus(saved, replay)).toBe(saved);
    expect(latestStatus(replay, saved)).toBe(saved);
  });

  it("начальный статус принимается как есть и не получает выдуманного времени", () => {
    const initial: WorkStatus = { status: "UNAVAILABLE", version: 0, changedAt: null };
    expect(latestStatus(null, initial)).toBe(initial);
    expect(statusSince(initial.changedAt)).toBe("");
    expect(statusChangedNote(initial.changedAt)).toBe("");
  });
});

describe("подписи статуса", () => {
  // Локальное время: формат не должен зависеть от часового пояса прогона.
  const now = new Date(2026, 9, 10, 15, 0);
  const today = new Date(2026, 9, 10, 9, 12).toISOString();
  const yesterday = new Date(2026, 9, 9, 18, 0).toISOString();
  const earlier = new Date(2026, 9, 3, 18, 0).toISOString();

  it("короткая форма есть только у «Готов принимать»", () => {
    expect(statusLabel("READY")).toBe("Готов принимать");
    expect(statusLabel("READY", true)).toBe("Готов");
    expect(statusLabel("BREAK", true)).toBe("Перерыв");
  });

  it("время изменения: сегодня, вчера и раньше", () => {
    expect(statusSince(today, now)).toBe("с 09:12");
    expect(statusSince(yesterday, now)).toBe("с вчера, 18:00");
    expect(statusSince(earlier, now)).toMatch(/^с 3 .+18:00$/);
    expect(statusChangedNote(today, now)).toBe("Изменён сегодня в 09:12.");
    expect(statusChangedNote(yesterday, now)).toBe("Изменён вчера в 18:00.");
    expect(statusChangedNote(earlier, now)).toMatch(/^Изменён 3 .+18:00\.$/);
  });

  it("присутствие дописывается только там, где расходится со статусом", () => {
    expect(presenceNote("BREAK", true)).toBe("в приложении");
    expect(presenceNote("UNAVAILABLE", true)).toBe("в приложении");
    expect(presenceNote("READY", false)).toBe("приложение закрыто");
    expect(presenceNote("BUSY", false)).toBe("приложение закрыто");
    expect(presenceNote("READY", true)).toBe("");
    expect(presenceNote("BUSY", true)).toBe("");
    expect(presenceNote("BREAK", false)).toBe("");
    expect(presenceNote("UNAVAILABLE", false)).toBe("");
  });
});
