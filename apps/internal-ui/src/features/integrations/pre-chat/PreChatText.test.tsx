import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { t } from "../../../i18n";
import { en } from "../../../i18n/en";
import { ru } from "../../../i18n/ru";
import { PreChatText } from "./PreChatText";

describe("PreChatText", () => {
  it("shows the markup hint between the consent field and the revision line", () => {
    const markup = renderToStaticMarkup(
      <PreChatText
        draft={{ preChat: { enabled: true, title: "", fields: [] }, consentText: "" }}
        version="v3" updatedAt="" busy={false} error=""
        onChange={() => undefined} onSave={() => undefined}
      />,
    );
    const hint = markup.indexOf(t("pre_chat.consent_hint"));
    expect(hint).toBeGreaterThan(markup.indexOf("</textarea>"));
    expect(hint).toBeLessThan(markup.indexOf(t("pre_chat.consent_revision", { version: "3" })));
    expect(markup).toContain('<small class="pre-chat-consent-hint"><svg');
  });

  it("keeps the hint in both dictionaries", () => {
    expect(ru["pre_chat.consent_hint"]).toBe(
      "Можно использовать ссылки, жирный и курсив, подчёркнутый, переносы, абзацы и списки (HTML). Остальная разметка покажется простым текстом.",
    );
    expect(en["pre_chat.consent_hint"]).toMatch(/\(HTML\)/);
  });
});
