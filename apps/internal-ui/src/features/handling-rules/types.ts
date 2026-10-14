export type RuleKind = "RECEIPT_CONFIRMATION" | "WAIT_EXCEEDED_NOTICE" | "REPLY_REMINDER" | "ASSIGNMENT_RETURN";
export type Recipient = "ASSIGNEE" | "CONVERSATION_GROUP" | "GROUP_SUPERVISORS" | "MANAGEMENT";
export type RuleConditions = { channelIds?: number[]; availableOnly?: boolean };
export type RuleValues = {
  enabled: boolean; delayMinutes: number | null; conditions: RuleConditions; recipients: Recipient[]; text: string;
};
export type HandlingRule = RuleValues & {
  kind: RuleKind; version: number; updatedAt: string | null; updatedBy: string;
  catalog: { conditions: string[]; recipients: Recipient[]; requiresText: boolean;
    maxDelayMinutes: number; maxTextLength: number; deadlinePlaceholder: string };
};
export type RuleErrors = Partial<Record<keyof RuleValues, string>> & { detail?: string };
export type RuleExecution = {
  id: number; rule: { kind: RuleKind; version: number }; action: string; conversationId: number;
  sourceEvent: { id: number; type: string; occurredAt: string }; startedAt: string;
  scheduledFor: string; finishedAt: string | null;
  status: "PENDING" | "EXECUTED" | "SKIPPED" | "FAILED";
  reason: string; reasonLabel: string; attempts: number; messageId: number | null; notificationId: number | null;
  recipients: { userId: number; name: string }[];
};
