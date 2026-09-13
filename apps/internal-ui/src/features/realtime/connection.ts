// Сокет рабочего места: один на сессию, по нему идут события и диалогов, и
// уведомлений. Второй сокет ради второго источника означал бы второе
// переподключение и вторую точку отказа на ровном месте.
//
// Здесь только провод: подключение, переподключение с отступом и склейка частых
// событий. Кто на что подписан — знает реестр (subscribers.ts), и знает
// независимо от того, открыт сокет или нет.

const RECONNECT_MIN_MS = 1000;
const RECONNECT_MAX_MS = 30000;
// Поток событий в оживлённой организации плотнее прежнего опроса: несколько
// сообщений подряд должны приводить к одному обновлению, а не к пяти.
const COALESCE_MS = 700;
// Раз в минуту сервер узнаёт, что рабочее место живо: по этому признаку
// очередь решает, есть ли кому заметить ждущий диалог. Без heartbeat
// оборванное соединение считалось бы присутствием до истечения ключа.
const HEARTBEAT_MS = 60000;

export type RealtimeMessage = { type: string; conversationId?: number };

export class RealtimeConnection {
  private socket: WebSocket | null = null;
  private closed = false;
  private retry = RECONNECT_MIN_MS;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private flushTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  /** Последнее событие каждого типа: за окно склейки важно только оно. */
  private pending = new Map<string, RealtimeMessage>();
  private watched: number | null = null;

  constructor(
    private readonly url: string,
    private readonly onMessage: (message: RealtimeMessage) => void,
    private readonly onConnectedChange: (connected: boolean) => void,
  ) {}

  open(): void {
    if (this.closed) return;
    const socket = new WebSocket(this.url);
    this.socket = socket;
    socket.onopen = () => {
      this.retry = RECONNECT_MIN_MS;
      this.onConnectedChange(true);
      this.startHeartbeat();
      // После обрыва подписка теряется вместе с сокетом — восстанавливаем её.
      if (this.watched !== null) this.send({ type: "watch", conversationId: this.watched });
    };
    socket.onmessage = (event) => this.receive(String(event.data));
    socket.onclose = () => {
      this.onConnectedChange(false);
      this.stopHeartbeat();
      this.socket = null;
      if (this.closed) return;
      // Отступ растёт до полуминуты: сервер мог уйти на перезапуск.
      this.reconnectTimer = setTimeout(() => this.open(), this.retry);
      this.retry = Math.min(this.retry * 2, RECONNECT_MAX_MS);
    };
    socket.onerror = () => socket.close();
  }

  close(): void {
    this.closed = true;
    this.stopHeartbeat();
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.flushTimer !== null) clearTimeout(this.flushTimer);
    this.flushTimer = null;
    this.socket?.close();
    this.socket = null;
  }

  /** Какой диалог открыт: событий по нему клиент и ждёт. */
  watch(conversationId: number | null): void {
    this.watched = conversationId;
    if (conversationId !== null) this.send({ type: "watch", conversationId });
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => this.send({ type: "ping" }), HEARTBEAT_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
  }

  private send(payload: object): void {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(payload));
  }

  private receive(data: string): void {
    const message = JSON.parse(data) as RealtimeMessage;
    if (!message.type) return;
    this.pending.set(message.type, message);
    if (this.flushTimer !== null) return;
    this.flushTimer = setTimeout(() => {
      this.flushTimer = null;
      const flushed = [...this.pending.values()];
      this.pending.clear();
      for (const item of flushed) this.onMessage(item);
    }, COALESCE_MS);
  }
}
