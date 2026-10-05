import type { SiteField } from "@chatballs/contracts";
import { afterEach, expect, it, vi } from "vitest";

import { isRecentSiteField, RECENT_SITE_FIELD_MS } from "./siteData";
import { subscribeSiteDataClock } from "./useSiteDataClock";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("обновляет часы на каждом истечении подсветки без запроса к серверу", () => {
  vi.useFakeTimers();
  vi.stubGlobal("window", globalThis);
  const updated = Date.parse("2026-09-30T15:40:00Z");
  vi.setSystemTime(updated + RECENT_SITE_FIELD_MS - 1000);
  const first: SiteField = { key: "status", label: "Статус", type: "enum", value: "done", display: "Готово", updatedAt: new Date(updated).toISOString() };
  const second = { ...first, key: "other", updatedAt: new Date(updated + 2000).toISOString() };
  const onTick = vi.fn();
  const stop = subscribeSiteDataClock([first, second], onTick);
  expect(isRecentSiteField(first, onTick.mock.lastCall![0])).toBe(true);
  vi.advanceTimersByTime(1000);
  expect(onTick).toHaveBeenCalledTimes(2);
  expect(isRecentSiteField(first, onTick.mock.lastCall![0])).toBe(false);
  expect(isRecentSiteField(second, onTick.mock.lastCall![0])).toBe(true);
  vi.advanceTimersByTime(2000);
  expect(onTick).toHaveBeenCalledTimes(3);
  expect(isRecentSiteField(second, onTick.mock.lastCall![0])).toBe(false);
  expect(vi.getTimerCount()).toBe(0);
  stop();
});

it("отменяет таймер при переключении контакта или размонтировании", () => {
  vi.useFakeTimers();
  vi.stubGlobal("window", globalThis);
  const now = Date.now();
  const row: SiteField = { key: "id", label: "ID", type: "string", value: "1", display: "1", updatedAt: new Date(now).toISOString() };
  const onTick = vi.fn();
  const stop = subscribeSiteDataClock([row], onTick);
  stop();
  vi.advanceTimersByTime(RECENT_SITE_FIELD_MS);
  expect(onTick).toHaveBeenCalledOnce();
  expect(vi.getTimerCount()).toBe(0);
});
