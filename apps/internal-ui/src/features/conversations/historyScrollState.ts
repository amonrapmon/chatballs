const LOAD_TRIGGER_PX = 240;
const STICK_TO_BOTTOM_PX = 200;

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
      node.scrollTop += node.scrollHeight - this.anchorHeight;
      this.anchorHeight = null;
    }

    // Собственную запись показываем и после чтения истории. Реплики другого
    // сотрудника и AI не прерывают чтение; проверяем всю полученную дельту.
    if (lastKey !== "" && lastKey !== this.lastKey && (this.lastKey === "" || this.following || this.ownAfterLast(entries))) {
      node.scrollTop = node.scrollHeight;
      this.following = true;
      this.anchorHeight = null;
    }

    this.firstKey = firstKey;
    this.lastKey = lastKey;
    // Пустая страница или ошибка догрузки тоже завершают ожидание якоря.
    if (!loadingOlder) this.anchorHeight = null;
  }

  onScroll(node: Viewport, options: { hasOlder: boolean; loadingOlder: boolean }): boolean {
    this.following = node.scrollHeight - node.scrollTop - node.clientHeight <= STICK_TO_BOTTOM_PX;
    if (!options.hasOlder || options.loadingOlder || this.anchorHeight !== null
      || node.scrollTop > LOAD_TRIGGER_PX) return false;
    this.anchorHeight = node.scrollHeight;
    return true;
  }

  private ownAfterLast(entries: readonly ScrollEntry[]): boolean {
    for (let index = entries.length - 1; index >= 0 && entries[index].key !== this.lastKey; index -= 1) {
      if (entries[index].own) return true;
    }
    return false;
  }
}
