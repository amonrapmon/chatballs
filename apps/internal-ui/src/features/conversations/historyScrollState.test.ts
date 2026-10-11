import { describe, expect, it } from "vitest";

import { HistoryScrollState } from "./historyScrollState";

type Entry = { key: string; own: boolean };
type Author = "CONTACT" | "OPERATOR" | "AI" | "COMMENT";
const VIEWER_ID = 7;
const entry = (id: number, author: Author = "CONTACT", authorUserId?: number): Entry => ({
  key: `${author === "COMMENT" ? "c" : "m"}${id}`,
  own: (author === "OPERATOR" || author === "COMMENT") && authorUserId === VIEWER_ID,
});

function setup() {
  const state = new HistoryScrollState();
  let top = 0;
  const node = {
    scrollHeight: 2000,
    clientHeight: 500,
    get scrollTop() { return top; },
    set scrollTop(value: number) { top = Math.max(0, Math.min(value, this.scrollHeight - this.clientHeight)); },
  };
  const entries: Entry[] = [entry(50)];
  let nextId = 50;
  const options = { conversationId: 1, entries, loadingOlder: false };
  const update = () => state.update(node, options);
  const scroll = (position: number, hasOlder = false) => {
    node.scrollTop = position;
    return state.onScroll(node, { hasOlder, loadingOlder: options.loadingOlder });
  };
  const append = (height: number, author: Author = "CONTACT", authorUserId?: number) => {
    nextId += 1;
    entries.push(entry(nextId, author, authorUserId));
    node.scrollHeight += height;
    update();
  };
  update();
  return { node, state, options, entries, update, scroll, append };
}

describe("прокрутка истории диалога", () => {
  it("показывает конец после асинхронной первой загрузки и смены диалога", () => {
    const { node, options, update, scroll } = setup();
    expect(node.scrollTop).toBe(1500);
    scroll(600);
    options.conversationId = 2;
    options.entries = [];
    update();
    node.scrollHeight = 2500;
    options.entries = [entry(90)];
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
    const { node, entries, update, scroll } = setup();
    scroll(600);
    entries.push(entry(51, "OPERATOR", 7), entry(52, "AI"));
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
    const { node, entries, update, scroll, options, append } = setup();
    expect(scroll(100, true)).toBe(true);
    expect(scroll(100, true)).toBe(false);
    options.loadingOlder = true;
    update();
    entries.unshift(entry(1));
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

  it("показывает собственный комментарий и не прерывает чтение чужим", () => {
    const { node, scroll, append } = setup();
    scroll(600);
    append(100, "COMMENT", 8);
    expect(node.scrollTop).toBe(600);
    append(100, "COMMENT", 7);
    expect(node.scrollTop).toBe(1700);
  });
});
