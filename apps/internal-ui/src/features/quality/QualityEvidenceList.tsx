import { fmt } from "../../i18n";
import { Icon } from "../../shared/icons";
import { pathFromRoute } from "../../router";
import type { QualityEvidence } from "./types";

export function QualityEvidenceList({ messages, organizationId }: { messages: QualityEvidence[]; organizationId: string }) {
  return <div className="quality-evidence">{messages.map(message => <a className="link is-muted has-icon" key={message.messageId}
    href={`${pathFromRoute("chat", message.conversationId, organizationId)}#message-${message.messageId}`}><Icon name="message" size={12} /><b>{fmt.time(message.createdAt)}</b><span>{message.text || message.transcript}</span></a>)}</div>;
}
