import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { JournalRows } from "./JournalRows";
import type { RuleExecution } from "./types";

const entry: RuleExecution = {
  id: 1, rule: { kind: "REPLY_REMINDER", version: 2 }, action: "REPLY_REMINDER", conversationId: 17,
  sourceEvent: { id: 5, type: "PUBLIC_REPLY", occurredAt: "2026-10-14T09:00:00Z" }, startedAt: "2026-10-14T09:00:00Z",
  scheduledFor: "2026-10-14T09:05:00Z", finishedAt: "2026-10-14T09:06:00Z", status: "FAILED",
  reason: "execution_error", reasonLabel: "Действие не удалось выполнить", attempts: 5,
  messageId: null, notificationId: null, recipients: [],
};

function render(value: RuleExecution) {
  return renderToStaticMarkup(<JournalRows entries={[value]} names={{ 17: "Мария" }} timezone="Europe/Moscow" openConversation={() => undefined} />);
}

describe("rule journal rows", () => {
  it("renders failure, safe reason and organization's time without raw API codes", () => {
    const html = render(entry);
    expect(html).toContain("Ошибка");
    expect(html).toContain("Действие не удалось выполнить");
    expect(html).toContain("12:06");
    for (const code of ["FAILED", "execution_error", "PUBLIC_REPLY", "REPLY_REMINDER"]) expect(html).not.toContain(code);
  });
  it("does not present the cancellation timestamp as an executed action", () => {
    const html = render({ ...entry, status: "SKIPPED", reason: "replied", reasonLabel: "Клиенту ответили" });
    expect(html).toContain("Отменено");
    expect(html).toContain("Клиенту ответили");
    expect(html).not.toContain("12:06");
  });
});
