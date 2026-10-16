const LOAD_TRIGGER_PX = 240;
// Допуск только на округление: даже в короткой ленте чтение выше низа
// не должно прерываться входящим сообщением.
const STICK_TO_BOTTOM_PX = 2;

type Viewport = Pick<HTMLDivElement, "scrollTop" | "scrollHeight" | "clientHeight">;
/** Строка ленты: сообщение или внутренний комментарий. own — запись самого читателя. */
export type ScrollEntry = { key: string; own: boolean };

/** Положение чтения запоминается до того, как новая реплика увеличит ленту. */
export class HistoryScrollState {
  private conversationId: number | null | undefined;
  private firstKey = "";
  private lastKey = "";
  private following = true;
  private anchorHeight: number | null = null;
  private anchorTop = 0;
  private contentHeight = 0;
  private viewportHeight = 0;

  update(node: Viewport, options: {
    conversationId: number | null;
    entries: readonly ScrollEntry[];
    loadingOlder: boolean;
  }): void {
    const { conversationId, entries, loadingOlder } = options;
    if (conversationId !== this.conversationId) {
      this.conversationId = conversationId;
      this.firstKey = "";
      this.lastKey = "";
      this.following = true;
      this.anchorHeight = null;
    }

    const firstKey = entries[0]?.key ?? "";
    const lastKey = entries[entries.length - 1]?.key ?? "";
    if (firstKey !== this.firstKey && this.anchorHeight !== null) {
      // Браузер мог уже сдвинуть scrollTop своим scroll anchoring.
      node.scrollTop = this.anchorTop + node.scrollHeight - this.anchorHeight;
      this.anchorHeight = null;
    }

    // Собственную запись показываем и после чтения истории. Реплики другого
    // сотрудника и AI не прерывают чтение; проверяем всю полученную дельту.
    if (lastKey !== "" && (this.following || (lastKey !== this.lastKey && (this.lastKey === "" || this.ownAfterLast(entries))))) {
      node.scrollTop = node.scrollHeight;
      this.following = true;
      this.anchorHeight = null;
    }

    this.firstKey = firstKey;
    this.lastKey = lastKey;
    // Пустая страница или ошибка догрузки тоже завершают ожидание якоря.
    if (!loadingOlder) this.anchorHeight = null;
    this.rememberViewport(node);
  }

  /** Поле письма, переносы строк и загрузка медиа меняют размеры без новых ключей. */
  resize(node: Viewport): void {
    if (this.following && this.lastKey !== "") node.scrollTop = node.scrollHeight;
    this.rememberViewport(node);
  }

  onScroll(node: Viewport, options: { hasOlder: boolean; loadingOlder: boolean }): boolean {
    // Событие от layout может прийти раньше ResizeObserver: оно не означает,
    // что читатель сам ушёл от низа после раскрытия редактора.
    if (node.scrollHeight !== this.contentHeight || node.clientHeight !== this.viewportHeight) {
      this.resize(node);
      return false;
    }
    this.following = node.scrollHeight - node.scrollTop - node.clientHeight <= STICK_TO_BOTTOM_PX;
    if (this.anchorHeight !== null) this.anchorTop = node.scrollTop;
    if (!options.hasOlder || options.loadingOlder || this.anchorHeight !== null
      || node.scrollTop > LOAD_TRIGGER_PX) return false;
    this.anchorHeight = node.scrollHeight;
    this.anchorTop = node.scrollTop;
    return true;
  }

  private rememberViewport(node: Viewport): void {
    // Новая реплика во время запроса истории не входит в высоту старой страницы.
    if (this.anchorHeight !== null) {
      this.anchorHeight = node.scrollHeight;
      this.anchorTop = node.scrollTop;
    }
    this.contentHeight = node.scrollHeight;
    this.viewportHeight = node.clientHeight;
  }

  private ownAfterLast(entries: readonly ScrollEntry[]): boolean {
    for (let index = entries.length - 1; index >= 0 && entries[index].key !== this.lastKey; index -= 1) {
      if (entries[index].own) return true;
    }
    return false;
  }
}
