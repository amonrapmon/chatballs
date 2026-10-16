import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useComposerModel } from "./useComposerModel";
import type { ComposerAudience } from "./ComposerAudienceBar";

const delivery = vi.hoisted(() => ({
  comment: vi.fn(async () => true),
  suggested: vi.fn(async () => {}),
  ordinary: vi.fn(async () => {}),
  file: vi.fn(async () => {}),
  unlink: vi.fn(),
  mail: vi.fn(async () => true),
}));
vi.mock("./model", () => ({
  sendOperatorMessage: delivery.ordinary,
  sendFileMessage: delivery.file,
  sendVoiceMessage: vi.fn(),
}));
vi.mock("./EmailContinuationContext", () => ({
  useEmailContinuation: () => ({
    busy: false, error: "", send: delivery.mail,
    options: { addresses: ["customer@example.org"], mailboxes: [{ id: 7 }], canSend: true },
  }),
}));
vi.mock("./useCommentSubmit", () => ({
  useCommentSubmit: () => ({ sending: false, errorText: "", submit: delivery.comment }),
}));
vi.mock("./useReplyAssistance", () => ({
  useReplyAssistance: () => ({
    linked: { suggestionId: "original-id", originalText: "Original draft" },
    send: delivery.suggested, unlink: delivery.unlink, insert: () => "Original draft",
  }),
}));
vi.mock("./useComposerTemplates", () => ({ useComposerTemplates: () => ({ unfilledKeys: [] }) }));
vi.mock("./useVoiceRecorder", () => ({ useVoiceRecorder: () => ({ state: "idle", supported: false }) }));

// Render real React state without mounting a UI or starting any API service.
function editor(audience: ComposerAudience, text: string, attachment = false, commentOnly = false) {
  let captured: ReturnType<typeof useComposerModel> | undefined;
  function Harness() {
    const model = useComposerModel({
      conversationId: 31, onSent: vi.fn(), onCommentSaved: vi.fn(), commentOnly,
    });
    if (attachment && !model.attachment && model.audience === "reply") {
      model.pickFile(new File(["attachment"], "reply.txt"));
    }
    if (model.text !== text) model.changeText(text);
    if (model.audience !== audience && !commentOnly) model.switchAudience(audience);
    captured = model;
    return null;
  }
  renderToStaticMarkup(<Harness />);
  return captured!;
}

describe("combined reply and comment editor", () => {
  it("supervision alone sends only internal comments and cannot select a public audience", async () => {
    const model = editor("reply", "Internal only", false, true);
    model.switchAudience("email");
    expect(model.audience).toBe("comment");
    await model.send();
    expect(delivery.comment).toHaveBeenCalledWith("Internal only");
    expect(delivery.mail).not.toHaveBeenCalled();
    expect(delivery.ordinary).not.toHaveBeenCalled();
    expect(delivery.suggested).not.toHaveBeenCalled();
  });
  beforeEach(() => vi.clearAllMocks());

  it("sends an edited linked draft only after manual submission", async () => {
    const model = editor("reply", "Edited reply");
    expect(delivery.suggested).not.toHaveBeenCalled();
    await model.send();
    expect(delivery.suggested).toHaveBeenCalledExactlyOnceWith("Edited reply");
    expect(delivery.comment).not.toHaveBeenCalled();
    expect(delivery.ordinary).not.toHaveBeenCalled();
  });

  it("sends a comment through its own API even when a draft and reply attachment exist", async () => {
    const model = editor("comment", "Internal discussion", true);
    expect(model.attachment).not.toBeNull();
    expect(model.mark).toBeNull();
    await model.send();
    expect(delivery.comment).toHaveBeenCalledExactlyOnceWith("Internal discussion");
    expect(delivery.suggested).not.toHaveBeenCalled();
    expect(delivery.ordinary).not.toHaveBeenCalled();
    expect(delivery.file).not.toHaveBeenCalled();
  });

  it("sends mail through its API without carrying the reply attachment or linked AI draft", async () => {
    const model = editor("email", "Email reply", true);
    expect(model.attachment).toBeNull();
    expect(model.mark).toBeNull();
    expect(delivery.mail).not.toHaveBeenCalled();
    await model.send();
    expect(delivery.mail).toHaveBeenCalledExactlyOnceWith({
      recipient: "customer@example.org", connectionId: 7, subject: "", text: "Email reply", file: null,
    });
    expect(delivery.suggested).not.toHaveBeenCalled();
    expect(delivery.comment).not.toHaveBeenCalled();
    expect(delivery.file).not.toHaveBeenCalled();
  });

  it("keeps incomplete template variables from reaching either audience", async () => {
    for (const audience of ["reply", "email", "comment"] as const) {
      await editor(audience, "Hello, {{client_name}}").send();
    }
    expect(delivery.comment).not.toHaveBeenCalled();
    expect(delivery.suggested).not.toHaveBeenCalled();
    expect(delivery.ordinary).not.toHaveBeenCalled();
    expect(delivery.mail).not.toHaveBeenCalled();
  });
});
