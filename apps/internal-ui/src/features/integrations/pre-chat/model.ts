import type { Integration } from "../model";
import type { SiteField } from "../site-fields/model";

export type PreChatField = { key: string; required: boolean };
export type PreChat = { enabled: boolean; title: string; fields: PreChatField[] };
export type PreChatDraft = { preChat: PreChat; consentText: string };
export const CONTACT_KEYS = ["name", "email", "phone"] as const;

export function readPreChat(config: Integration["config"]): PreChatDraft {
  return {
    preChat: config.preChat ?? { enabled: false, title: "", fields: [] },
    consentText: config.consentText ?? "",
  };
}

export function availableFields(fields: PreChatField[], schema: SiteField[]): PreChatField[] {
  const allowed = new Set<string>([...CONTACT_KEYS, ...schema.map(({ key }) => key)]);
  return fields.filter(({ key }) => allowed.has(key));
}

export function selectField(fields: PreChatField[], key: string, selected: boolean): PreChatField[] {
  if (!selected) return fields.filter((field) => field.key !== key);
  return fields.some((field) => field.key === key) ? fields : [...fields, { key, required: false }];
}

export function preChatConfig(config: Integration["config"], draft: PreChatDraft) {
  return {
    ...config,
    preChat: { ...draft.preChat, title: draft.preChat.title.trim(), fields: availableFields(draft.preChat.fields, config.fields ?? []) },
    consentText: draft.consentText.trim(),
  };
}
