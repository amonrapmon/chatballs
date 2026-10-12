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
}));
vi.mock("./model", () => ({
  sendOperatorMessage: delivery.ordinary,
  sendFileMessage: delivery.file,
  sendVoiceMessage: vi.fn(),
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
function editor(audience: ComposerAudience, text: string, attachment = false) {
  let captured: ReturnType<typeof useComposerModel> | undefined;
  function Harness() {
    const model = useComposerModel({
      conversationId: 31, onSent: vi.fn(), onCommentSaved: vi.fn(),
    });
    if (attachment && !model.attachment && model.audience === "reply") {
      model.pickFile(new File(["attachment"], "reply.txt"));
    }
    if (model.text !== text) model.changeText(text);
    if (model.audience !== audience) model.switchAudience(audience);
    captured = model;
    return null;
  }
  renderToStaticMarkup(<Harness />);
  return captured!;
}

describe("combined reply and comment editor", () => {
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

  it("keeps incomplete template variables from reaching either audience", async () => {
    for (const audience of ["reply", "comment"] as const) {
      await editor(audience, "Hello, {{client_name}}").send();
    }
    expect(delivery.comment).not.toHaveBeenCalled();
    expect(delivery.suggested).not.toHaveBeenCalled();
    expect(delivery.ordinary).not.toHaveBeenCalled();
  });
});