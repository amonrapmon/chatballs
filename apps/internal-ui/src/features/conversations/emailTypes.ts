export type Mailbox = { id: number; name: string; address: string };
export type EmailOptions = { addresses: string[]; mailboxes: Mailbox[] };
export type EmailState = "PENDING" | "SENDING" | "SMTP_ACCEPTED" | "FAILED" | "UNKNOWN";
export type EmailAttempt = {
  id: number; number: number; state: EmailState; initiatedById: number; initiatedByName: string;
  errorCode: string; errorMessage: string; createdAt: string; startedAt: string | null; finishedAt: string | null;
};
export type EmailOperation = {
  id: number; messageId: number; threadId: number; connectionId: number; recipient: string; subject: string;
  senderAddress: string | null; mailboxName: string | null; createdAt: string;
  retryAllowed: boolean; deliveryConfirmed: boolean; attempts: EmailAttempt[];
};
export type EmailDraft = { recipient: string; connectionId: number; subject: string; text: string; file: File | null };
export type VisitorObservation = {
  tabId: string; sequence: number; widget: "unknown" | "open" | "closed";
  page: "unknown" | "visible" | "hidden" | "frozen" | "resumed" | "pagehide" | "pageshow";
  connection: "unknown" | "connected" | "lost"; departure: "unknown";
  receivedAt: string; heartbeatAt: string | null;
  widgetChangedAt: string | null; pageChangedAt: string | null; connectionChangedAt: string | null;
};
export type VisitorState = { sessions: Array<{ heartbeatIntervalSeconds: number; heartbeatTimeoutSeconds: number; tabs: VisitorObservation[] }> };
