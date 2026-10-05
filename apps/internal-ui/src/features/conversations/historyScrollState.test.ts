import { describe, expect, it } from "vitest";

import { HistoryScrollState } from "./historyScrollState";

type Message = { id: number; author: "CONTACT" | "OPERATOR" | "AI"; authorUserId?: number };

function setup() {
  const state = new HistoryScrollState();
  let top = 0;
  const node = {
    scrollHeight: 2000,
    clientHeight: 500,
    get scrollTop() { return top; },
    set scrollTop(value: number) { top = Math.max(0, Math.min(value, this.scrollHeight - this.clientHeight)); },
  };
  const messages: Message[] = [{ id: 50, author: "CONTACT" }];
  const options = { conversationId: 1, messages, viewerId: 7, loadingOlder: false };
  const update = () => state.update(node, options);
  const scroll = (position: number, hasOlder = false) => {
    node.scrollTop = position;
    return state.onScroll(node, { hasOlder, loadingOlder: options.loadingOlder });
  };
  const append = (height: number, author: Message["author"] = "CONTACT", authorUserId?: number) => {
    messages.push({ id: messages[messages.length - 1].id + 1, author, authorUserId });
    node.scrollHeight += height;
    update();
  };
  update();
  return { node, state, options, messages, update, scroll, append };
}

describe("прокрутка истории диалога", () => {
  it("показывает конец после асинхронной первой загрузки и смены диалога", () => {
    const { node, options, update, scroll } = setup();
    expect(node.scrollTop).toBe(1500);
    scroll(600);
    options.conversationId = 2;
    options.messages = [];
    update();
    node.scrollHeight = 2500;
    options.messages = [{ id: 90, author: "CONTACT" }];
    update();
    expect(node.scrollTop).toBe(2000);
  });

  it("следует за короткими и длинными входящими сообщениями у низа ленты", () => {
    const { node, scroll, append } = setup();
    scroll(1500);
    append(80);
    expect(node.scrollTop).toBe(1580);
    append(900);
    expect(node.scrollTop).toBe(2480);
    append(80);
    expect(node.scrollTop).toBe(2560);
  });

  it("учитывает близость к низу до добавления длинного сообщения", () => {
    const { node, scroll, append } = setup();
    scroll(1350);
    append(900);
    expect(node.scrollTop).toBe(2400);
  });

  it("сохраняет место чтения при входящих и чужих исходящих сообщениях", () => {
    const { node, scroll, append } = setup();
    scroll(600);
    append(100);
    append(100, "OPERATOR", 8);
    append(100, "AI");
    expect(node.scrollTop).toBe(600);
  });

  it("показывает собственный ответ даже если в той же дельте пришёл ответ AI", () => {
    const { node, messages, update, scroll } = setup();
    scroll(600);
    messages.push({ id: 51, author: "OPERATOR", authorUserId: 7 }, { id: 52, author: "AI" });
    node.scrollHeight += 400;
    update();
    expect(node.scrollTop).toBe(1900);
  });

  it("возобновляет следование после ручного возвращения к последней реплике", () => {
    const { node, scroll, append } = setup();
    scroll(600);
    append(100);
    scroll(1600);
    append(300);
    expect(node.scrollTop).toBe(1900);
  });

  it("догружает предыдущую страницу один раз и сохраняет место чтения", () => {
    const { node, messages, update, scroll, options, append } = setup();
    expect(scroll(100, true)).toBe(true);
    expect(scroll(100, true)).toBe(false);
    options.loadingOlder = true;
    update();
    messages.unshift({ id: 1, author: "CONTACT" });
    node.scrollHeight += 1200;
    update();
    expect(node.scrollTop).toBe(1300);
    options.loadingOlder = false;
    update();
    append(100);
    expect(node.scrollTop).toBe(1300);
  });

  it("разрешает повторную догрузку после ошибки или пустой страницы", () => {
    const { node, update, scroll, options, append } = setup();
    expect(scroll(100, true)).toBe(true);
    options.loadingOlder = true;
    update();
    options.loadingOlder = false;
    update();
    expect(scroll(100, true)).toBe(true);
    append(100, "OPERATOR", 7);
    expect(node.scrollTop).toBe(1600);
  });
});
