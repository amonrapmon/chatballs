import { describe, expect, it } from "vitest";

import { resolveAudioMode } from "./AudioCallOverlay";
import type { ApiCall } from "./model";

// Экран аудиозвонка у оператора: что он показывает в каждой фазе.

function call(status: ApiCall["status"]): ApiCall {
  return { id: "c1", conversationId: 1, status, kind: "AUDIO", connectedAt: null, endedBy: null, durationSeconds: null } as ApiCall;
}

describe("resolveAudioMode", () => {
  it("показывает разговор, пока звонок идёт", () => {
    expect(resolveAudioMode(call("ACTIVE"), "", "connected", "none")).toBe("active");
  });

  it("считает звонок завершённым, даже когда соединение ещё считает себя живым", () => {
    // Клиент положил трубку: сервер уже в терминале, а peer connection узнаёт
    // об этом позже — или не узнаёт вовсе, если сокет мёртв.
    expect(resolveAudioMode(call("ENDED"), "", "connected", "none")).toBe("status");
    expect(resolveAudioMode(call("DECLINED"), "", "connected", "none")).toBe("status");
    expect(resolveAudioMode(call("FAILED"), "", "connected", "none")).toBe("status");
  });

  it("до ответа клиента звонок исходящий", () => {
    expect(resolveAudioMode(call("RINGING"), "", "idle", "none")).toBe("ringing");
  });

  it("принятый звонок без соединения — соединение", () => {
    expect(resolveAudioMode(call("ACCEPTED"), "", "idle", "none")).toBe("connecting");
  });
});
