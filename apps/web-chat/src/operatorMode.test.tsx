import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import type { WebConfig } from "./api";
import { ChatBody } from "./ChatBody";
import { applyWidgetLanguage } from "./i18n";

it("shows the company greeting and operator waiting without an AI author or typing", () => {
  applyWidgetLanguage("ru");
  const config: WebConfig = { available: true, autonomous: false, title: "Support", greeting: "Welcome" };
  const html = renderToStaticMarkup(<ChatBody config={config} bodyRef={{ current: null }} unavailable={false}
    accepted accent="#1677ff" title="Support" messages={[]} pending={[]} awaiting={false} state="waiting"
    lastContactRequestId={0} showPhoneForm={false} onSubmitContact={async () => true} />);
  expect(html).toContain("Welcome");
  expect(html).toContain("Ожидаем ответа сотрудника");
  expect(html).not.toContain("печатает");
  expect(html).not.toContain("wcTyping");
  expect(html).not.toContain("Передаём оператору");
});
