import { useEffect, useState } from "react";

import type { UpdateInfo } from "./api";

// Ход установки для интерфейса. Сервис обновления пишет стадию словом в
// status.json (starting → downloading → pulling → restarting → updated), и это
// единственное, что о ходе вообще известно: процента у docker pull здесь нет.
// Поэтому прогресс показывается стадиями — человек видит, что именно идёт
// сейчас и сколько таких шагов осталось, а не безымянную полосу.

export const STAGES = ["starting", "downloading", "pulling", "restarting"] as const;

export type Stage = (typeof STAGES)[number];

function isStage(value: string): value is Stage {
  return (STAGES as readonly string[]).includes(value);
}

/**
 * Текущая стадия.
 *
 * Молчание бэкенда во время установки — это и есть перезапуск: он сам входит в
 * перезапускаемый стек и последнюю стадию сообщить уже не может.
 */
export function stageOf(info: UpdateInfo | null, unreachable: boolean): Stage {
  if (unreachable) return "restarting";
  const message = info?.install.message ?? "";
  return isStage(message) ? message : "starting";
}

export function stageNumber(stage: Stage): number {
  return STAGES.indexOf(stage) + 1;
}

/** Доля выполненного: последняя стадия не доводится до края, пока не готово. */
export function stageProgress(stage: Stage): number {
  return Math.round(((stageNumber(stage) - 0.35) / STAGES.length) * 100);
}

/** Секунды с момента запуска установки; тикает раз в секунду. */
export function useElapsed(startedAt: string | null, running: boolean): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  if (!startedAt) return 0;
  const started = new Date(startedAt).getTime();
  if (Number.isNaN(started)) return 0;
  return Math.max(0, Math.floor((now - started) / 1000));
}

/** м:сс — установка идёт минуты, часы здесь не нужны. */
export function clockLabel(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}
