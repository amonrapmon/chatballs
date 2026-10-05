import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ChatHeader } from "./ChatHeader";
import { Bubble } from "./ChatMessages";
import { ChatComposer } from "./ChatComposer";
import { PhoneForm } from "./PhoneForm";
import { StartChatFooter } from "./StartChatFooter";
import { WidgetStyles } from "./WidgetStyles";
import { resolveWidgetAppearance } from "./widgetAppearance";
import { widgetClasses as classes } from "./widgetClasses";

describe("widget appearance", () => {
  it("keeps legacy/default accent and gives appearance precedence", () => {
    expect(resolveWidgetAppearance(null).accent).toBe("#1677ff");
    expect(resolveWidgetAppearance({ available: true, accent: "#4f46e5" }).accent).toBe("#4f46e5");
    expect(resolveWidgetAppearance({ available: true, accent: "#4f46e5", appearance: { accent: "#0d8a7e" } }).accent).toBe("#0d8a7e");
  });

  it("renders the default mark, inherited icon, own icon and no icon", () => {
    for (const [appearance, expected] of [
      [{}, ""],
      [{ launcherIcon: "/launcher.png" }, "/launcher.png"],
      [{ launcherIcon: "/launcher.png", headerIcon: "" }, "/launcher.png"],
      [{ launcherIcon: "/launcher.png", headerIcon: "/header.svg" }, "/header.svg"],
      [{ launcherIcon: "/launcher.png", headerIcon: null }, null],
    ] as const) {
      const { headerIcon } = resolveWidgetAppearance({ available: true, appearance });
      expect(headerIcon).toBe(expected);
      const html = renderToStaticMarkup(<ChatHeader accent="#1677ff" icon={headerIcon} title="" expanded={false} canExpand={false} onToggleExpand={() => {}} onClose={() => {}} />);
      expect(html.includes(classes.headerIcon)).toBe(expected !== null);
      if (expected) expect(html).toContain(`src="${expected}"`);
      if (expected === "") expect(html).toContain("<mask");
      if (expected === null) expect(html).not.toContain("<mask");
    }
  });

  it("exposes overridable hooks on client, AI and operator bubbles", () => {
    for (const author of ["client", "ai", "operator"] as const) {
      const html = renderToStaticMarkup(<Bubble author={author} authorName="" text="" accent="#1677ff" />);
      expect(html).toContain(author === "client" ? classes.bubbleClient : classes.bubbleAgent);
      if (author === "operator") expect(html).toContain(classes.bubbleOperator);
      const bubbleTag = html.match(/<div class="cb-bubble [^>]+>/)?.[0];
      expect(bubbleTag).toBeDefined();
      expect(bubbleTag).not.toContain("background:");
      expect(bubbleTag).not.toContain("border-radius:");
    }
  });

  it("exposes input/start/form hooks without inline base styles", () => {
    const html = renderToStaticMarkup(<>
      <ChatComposer accent="#1677ff" input="" onInput={() => {}} onSend={() => {}} />
      <StartChatFooter accent="#1677ff" starting={false} onAccept={() => {}} />
      <PhoneForm accent="#1677ff" onSubmit={async () => true} />
    </>);
    for (const hook of [classes.composer, classes.composerInput, classes.startButton, classes.formField]) expect(html).toContain(`class="${hook}"`);
    expect(html).not.toContain("border-radius:");
  });

  it("places the baseline sample after zero-specificity base styles as text", () => {
    const css = '.cb-header { font-family: "PT Sans", sans-serif; }\n.cb-bubble--client { border-radius: 18px 4px 18px 18px; }\n.cb-start-button { text-transform: uppercase; }';
    const html = renderToStaticMarkup(<WidgetStyles customCss={css} />);
    expect(html.indexOf('data-cb-styles="custom"')).toBeGreaterThan(html.indexOf('data-cb-styles="base"'));
    expect(html).toContain(":where(.cb-header)");
    expect(html).toContain(css);
    const escaped = renderToStaticMarkup(<WidgetStyles customCss="</style><script>alert(1)</script>" />);
    expect(escaped).not.toContain("</style><script>");
  });
});
