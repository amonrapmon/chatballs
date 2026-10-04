import { renderToStaticMarkup } from "react-dom/server";
import { beforeAll, describe, expect, it } from "vitest";

import type { WebConfig } from "./api";
import { ChatBody } from "./ChatBody";
import { ConsentText } from "./ConsentText";
import { PreChatForm } from "./PreChatForm";
import { applyWidgetLanguage } from "./i18n";
import { widgetClasses as classes } from "./widgetClasses";

const LINK = '<a href="https://example.ru/privacy" target="_blank" rel="noopener noreferrer nofollow">политику обработки данных</a>';
const RICH = `Нажимая «Начать чат», вы принимаете ${LINK}.<br><strong>Что мы храним:</strong><ul><li>имя и контакты;</li><li>историю диалога.</li></ul>`;
const PLAIN = "Продолжая, вы соглашаетесь на обработку сообщений.";

function config(text: string): WebConfig {
  return { available: true, title: "Помощник", greeting: "Здравствуйте!", consent: { text, version: "v3" } };
}

function screen(text: string): string {
  return renderToStaticMarkup(<ChatBody bodyRef={{ current: null }} config={config(text)} unavailable={false} accepted={false} accent="#1677ff" title="Помощник" messages={[]} pending={[]} awaiting={false} lastContactRequestId={0} showPhoneForm={false} onSubmitContact={async () => true} />);
}

function form(text: string): string {
  return renderToStaticMarkup(<PreChatForm config={{ ...config(text), preChat: { enabled: true, title: "", fields: [] } }} accent="#1677ff" title="Помощник" siteValues={{}} starting={false} onAccept={async () => {}} />);
}

describe("consent text", () => {
  beforeAll(() => applyWidgetLanguage("ru"));

  it("shows text without tags as before, with the revision at the end of the line", () => {
    expect(screen(PLAIN)).toContain(`${PLAIN}</span> · ред. v3</div>`);
    expect(form(PLAIN)).toContain(`${PLAIN}</span> · редакция v3</div>`);
    for (const html of [screen(PLAIN), form(PLAIN)]) expect(html).not.toContain(classes.consentRevision);
  });

  it("renders sanitized markup on the consent screen and in the pre-chat form", () => {
    for (const html of [screen(RICH), form(RICH)]) {
      expect(html).toContain(LINK);
      expect(html).toContain("<br><strong>Что мы храним:</strong><ul><li>имя и контакты;</li>");
      expect(html).not.toContain("&lt;");
    }
  });

  it("keeps the revision inline for one line and moves it below paragraphs, breaks and lists", () => {
    const inline = `Вы принимаете ${LINK} и <strong>запись чата</strong>`;
    expect(screen(inline)).toContain("</strong></span> · ред. v3</div>");
    expect(screen(RICH)).toContain(`</ul></div><div class="${classes.consentRevision}">Ред. v3</div>`);
    expect(form(RICH)).toContain(`</ul></div><div class="${classes.consentRevision}">Редакция v3</div>`);
    for (const text of ["Первая<br>вторая", "<p>Абзац</p>", "<ol><li>Пункт</li></ol>"]) {
      expect(screen(text)).toContain(`class="${classes.consentRevision}"`);
      expect(screen(text)).not.toContain(" · ");
    }
  });

  it("goes through one shared component with the form's own spacing hook", () => {
    const shared = renderToStaticMarkup(<ConsentText consent={config(RICH).consent} place="screen" />);
    expect(screen(RICH)).toContain(shared);
    expect(form(RICH)).toContain(`class="${classes.consent} ${classes.preChatConsent}"`);
  });
});
