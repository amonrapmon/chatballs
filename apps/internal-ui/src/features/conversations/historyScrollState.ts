import type { ApiMessage } from "./apiTypes";

const LOAD_TRIGGER_PX = 240;
const STICK_TO_BOTTOM_PX = 200;

type Viewport = Pick<HTMLDivElement, "scrollTop" | "scrollHeight" | "clientHeight">;
type Message = Pick<ApiMessage, "id" | "author" | "authorUserId">;

/** Положение чтения запоминается до того, как новая реплика увеличит ленту. */
export class HistoryScrollState {
  private conversationId: number | null | undefined;
  private firstId = 0;
  private lastId = 0;
  private following = true;
  private anchorHeight: number | null = null;

  update(node: Viewport, options: {
    conversationId: number | null;
    messages: Message[];
    viewerId: number | null;
    loadingOlder: boolean;
  }): void {
    const { conversationId, messages, viewerId, loadingOlder } = options;
    if (conversationId !== this.conversationId) {
      this.conversationId = conversationId;
      this.firstId = 0;
      this.lastId = 0;
      this.following = true;
      this.anchorHeight = null;
    }

    const firstId = messages[0]?.id ?? 0;
    const lastId = messages[messages.length - 1]?.id ?? 0;
    if (firstId !== this.firstId && this.anchorHeight !== null) {
      node.scrollTop += node.scrollHeight - this.anchorHeight;
      this.anchorHeight = null;
    }

    // Собственный ответ показываем и после чтения истории. Реплики другого
    // сотрудника и AI не прерывают чтение; проверяем всю полученную дельту.
    const ownReply = this.lastId !== 0 && viewerId !== null && messages.some(
      (message) => message.id > this.lastId
        && message.author === "OPERATOR" && message.authorUserId === viewerId,
    );
    if (lastId !== 0 && lastId !== this.lastId && (this.lastId === 0 || this.following || ownReply)) {
      node.scrollTop = node.scrollHeight;
      this.following = true;
      this.anchorHeight = null;
    }

    this.firstId = firstId;
    this.lastId = lastId;
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
}
