import type { preChatRu } from "./pre-chat.ru";

export const preChatEn: Record<keyof typeof preChatRu, string> = {
  "pre_chat.description": "Replaces the consent screen with fields, consent text and the “Start chat” button. If a value has already arrived from the website, the field is prefilled and the customer can edit it.",
  "pre_chat.enabled": "Request details at the start of a conversation",
  "pre_chat.disabled_hint": "When disabled, the customer sees consent and starts chatting",
  "pre_chat.field": "FIELD",
  "pre_chat.source": "SOURCE",
  "pre_chat.required": "REQUIRED",
  "pre_chat.required_label": "Required: {label}",
  "pre_chat.name": "Name",
  "pre_chat.email": "Email",
  "pre_chat.phone": "Phone",
  "pre_chat.site_source": "{key} · from website",
  "pre_chat.custom": "custom field",
  "pre_chat.add_custom": "Custom field from “Website data”",
  "pre_chat.types_hint": "Yes/No and List types use a switch and a dropdown",
  "pre_chat.title": "Form title",
  "pre_chat.consent": "Consent text",
  "pre_chat.consent_revision": "Revision {version} · changing the text increases the revision; customers with earlier consent will see the form again",
  "pre_chat.on": "on",
  "pre_chat.saved_today": "saved today, {time}",
};
