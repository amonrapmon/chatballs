import type { RealtimeMessage } from "./connection";

// Реестр подписчиков живёт отдельно от сокета и переживает его обрывы: подписка
// оформляется в момент монтирования компонента, а сокет к этому моменту может
// быть ещё не открыт или уже переподключаться. Связывать одно с другим — значит
// терять события на каждом обрыве.

export type RealtimeHandler = (message: RealtimeMessage) => void;

export class RealtimeSubscribers {
  private handlers = new Map<string, Set<RealtimeHandler>>();

  subscribe(type: string, handler: RealtimeHandler): () => void {
    const forType = this.handlers.get(type) ?? new Set<RealtimeHandler>();
    forType.add(handler);
    this.handlers.set(type, forType);
    return () => {
      forType.delete(handler);
    };
  }

  dispatch(message: RealtimeMessage): void {
    for (const handler of this.handlers.get(message.type) ?? []) handler(message);
  }
}
