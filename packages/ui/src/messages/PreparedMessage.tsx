import { useEffect, useRef, useState } from "react";
import type { MessagePresentation } from "@chatballs/contracts";
import "./prepared-message.css";
import { snapshotDocument, snapshotText } from "./snapshot";
import { preserveSnapshotScroll } from "./preserveSnapshotScroll";

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
  const documentSource = snapshotDocument(content, mode);
  useEffect(() => () => observer.current?.disconnect(), [documentSource]);
  function measure() {
    observer.current?.disconnect();
    const document = frame.current?.contentDocument;
    if (!document) return;
    const update = () => {
      const restore = preserveSnapshotScroll(frame.current);
      setHeight(Math.ceil(Math.max(document.body.scrollHeight,
        document.body.getBoundingClientRect().height, document.documentElement.scrollHeight)));
      requestAnimationFrame(restore);
    };
    update();
    observer.current = new ResizeObserver(update);
    observer.current.observe(document.body);
  }
  if (!documentSource) return <div className="prepared-message-text">{snapshotText(content.text)}</div>;
  return <div className="prepared-message" style={{ height }}>
    <iframe className="prepared-message-measure" ref={frame} aria-hidden="true" tabIndex={-1}
      sandbox="allow-same-origin" referrerPolicy="no-referrer" srcDoc={documentSource}
      title={title} onLoad={measure} />
    <iframe className="prepared-message-frame" sandbox="" referrerPolicy="no-referrer"
      srcDoc={documentSource} title={title} style={{ height }} />
  </div>;
}
