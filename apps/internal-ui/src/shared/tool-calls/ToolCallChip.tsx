import { useId, useState } from "react";

import { fmt, t, tn } from "../../i18n";
import { Icon } from "../icons";
import { toolCallDetail, toolDuration, type ToolCall } from "./model";
import "./styles.css";

/** Calls of one turn; test-chat can pass the calls of one HTTP response. */
export function ToolCallChip({ calls, createdAt }: { calls: readonly ToolCall[]; createdAt: string }) {
  const [expanded, setExpanded] = useState(false);
  const listId = useId();
  if (!calls.length) return null;
  const multiple = calls.length > 1;
  const errors = calls.filter((call) => !call.ok).length;
  const duration = toolDuration(calls.reduce((total, call) => total + call.durationMs, 0));
  const text = multiple
    ? [tn("tool_calls.requested_count", calls.length), errors ? tn("tool_calls.error_count", errors) : "", duration].filter(Boolean).join(" · ")
    : t("tool_calls.requested", { detail: toolCallDetail(calls[0]) });
  const heading = <><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z" /></svg><span>{text} · {fmt.time(createdAt)}</span></>;

  return (
    <div className={`tool-call-chip${multiple ? " is-group" : ""}${errors ? " is-error" : ""}`}>
      {multiple ? (
        <button type="button" className="tool-call-heading" aria-expanded={expanded} aria-controls={listId} onClick={() => setExpanded(!expanded)}>
          {heading}<Icon name="chevron" size={11} strokeWidth={2.4} />
        </button>
      ) : <span className="tool-call-heading">{heading}</span>}
      {multiple && expanded && (
        <ul id={listId} className="tool-call-list">
          {calls.map((call, index) => <li key={index} className={call.ok ? "" : "is-error"}><i />{toolCallDetail(call)}</li>)}
        </ul>
      )}
    </div>
  );
}
