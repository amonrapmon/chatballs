import { createRef } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ChatBody } from "./ChatBody";

describe("participant messages in customer history", () => {
  it("renders each employee's own name and the public notice without its event code", () => {
    const html = renderToStaticMarkup(<ChatBody
      bodyRef={createRef()} config={{ available: true }} unavailable={false} accepted
      accent="#1677ff" title="Ассистент" pending={[]} awaiting={false}
      lastContactRequestId={0} showPhoneForm={false} onSubmitContact={async () => true}
      messages={[
        { id: 1, author: "operator", authorName: "Анна Ким", text: "Первый ответ", createdAt: "2026-10-12T10:00:00Z" },
        { id: 2, author: "system", systemEvent: "specialist_joined", text: "К диалогу подключился специалист Мария.", createdAt: "2026-10-12T10:01:00Z" },
        { id: 3, author: "operator", authorName: "Мария", text: "Второй ответ", createdAt: "2026-10-12T10:02:00Z" },
      ]}
    />);
    expect(html).toContain("Анна Ким");
    expect(html).toContain("Мария</small>");
    expect(html).toContain("К диалогу подключился специалист Мария.");
    expect(html).toContain("background:#eceef2");
    expect(html).not.toContain("specialist_joined");
  });
});
