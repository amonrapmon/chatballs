import { useEffect, useRef, useState } from "react";
import type { MessagePresentation } from "@chatballs/contracts";
import "./prepared-message.css";

export type PreparedContent = MessagePresentation & { text: string };

/** Only server-prepared snapshots cross this boundary; never pass editor source.
 * The visible document always has an opaque origin and an empty sandbox.
 * A noninteractive, scriptless measuring document supplies intrinsic height.
 * It has no allow-scripts, forms, popups or navigation permissions, and retains
 * the server CSP. No observer or other executable code is injected into it.
 */
export function PreparedMessage({ content, mode, title }: {
  content: PreparedContent;
  mode?: "html" | "text";
  title: string;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const observer = useRef<ResizeObserver | null>(null);
  const [height, setHeight] = useState(0);
  const presentation = content.presentation;
  const representation = mode ?? content.deliveryRepresentation ?? "html";
  const html = representation === "html" && presentation?.formatVersion === 1
    && presentation.isolation === "sandboxed-iframe" && presentation.sandbox === "";
  useEffect(() => () => observer.current?.disconnect(), []);
  function measure() {
    observer.current?.disconnect();
    const document = frame.current?.contentDocument;
    if (!document) return;
    const update = () => setHeight(Math.ceil(Math.max(document.body.scrollHeight,
      document.body.getBoundingClientRect().height, document.documentElement.scrollHeight)));
    update();
    observer.current = new ResizeObserver(update);
    observer.current.observe(document.body);
  }
  if (!html) return <div className="prepared-message-text">{content.text}</div>;
  return <div className="prepared-message" style={{ height }}>
    <iframe className="prepared-message-measure" ref={frame} aria-hidden="true" tabIndex={-1}
      sandbox="allow-same-origin" referrerPolicy="no-referrer" srcDoc={presentation.srcDoc}
      title={title} onLoad={measure} />
    <iframe className="prepared-message-frame" sandbox="" referrerPolicy="no-referrer"
      srcDoc={presentation.srcDoc} title={title} style={{ height }} />
  </div>;
}
