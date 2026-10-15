import { useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EmailDraft, EmailOptions } from "./emailTypes";
import { useEmailComposerDraft } from "./useEmailComposerDraft";

const mail = vi.hoisted(() => ({ options: null as EmailOptions | null, send: vi.fn(async (_draft: EmailDraft) => true) }));
vi.mock("./EmailContinuationContext", () => ({
  useEmailContinuation: () => ({ options: mail.options, busy: false, send: mail.send }),
}));
const first = { id: 7, name: "Support", address: "support@example.org" };
const second = { id: 8, name: "Office", address: "office@example.org" };
const options = (mailboxes = [first, second]): EmailOptions => ({ addresses: ["customer@example.org"], mailboxes });

// React повторяет render при выборе ящика. Следующие render имитируют обновление
// options в существующем контексте, без API-сервера или сетевых ответов.
function draft(sequence: Array<EmailOptions | null>, selectedId = 8) {
  const snapshots: Array<ReturnType<typeof useEmailComposerDraft>> = [];
  function Harness() {
    const [phase, setPhase] = useState(0);
    mail.options = sequence[Math.max(0, phase - 1)];
    const model = useEmailComposerDraft(31);
    if (phase === 0) {
      model.setConnectionId(selectedId);
      model.setText("Mail draft");
      model.setSubject("Subject");
    } else snapshots.push(model);
    if (phase < sequence.length) setPhase(phase + 1);
    return null;
  }
  renderToStaticMarkup(<Harness />);
  return snapshots;
}

beforeEach(() => { mail.send.mockClear(); });

describe("selected mailbox in a mail draft", () => {
  it("keeps the selected mailbox through option refresh and sends its id", async () => {
    const models = draft([options(), options([second, first]), options()]);
    expect(models.map((model) => model.mailbox?.id)).toEqual([8, 8, 8]);
    expect(await models[2].send()).toBe(true);
    expect(mail.send).toHaveBeenCalledWith({ recipient: "customer@example.org", connectionId: 8,
      subject: "Subject", text: "Mail draft", file: null });
  });

  it("blocks sending while the selected mailbox is unavailable and restores the selection", async () => {
    const models = draft([options(), options([first]), null, options()]);
    expect(models.map((model) => model.mailbox?.id)).toEqual([8, undefined, undefined, 8]);
    expect(models[1].blocked).toBe(true);
    expect(await models[1].send()).toBe(false);
    expect(await models[2].send()).toBe(false);
    expect(mail.send).not.toHaveBeenCalled();
    expect(models[3].text).toBe("Mail draft");
    expect(await models[3].send()).toBe(true);
    expect(mail.send.mock.calls[0][0].connectionId).toBe(8);
  });
});
