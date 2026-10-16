import logoSource from "./branding/logo-sunset.svg?raw";
import logoReference from "../../../../design/baseline/platform-expansion/assets/logo-sunset.svg?raw";
import chatReference from "../../../../design/baseline/platform-expansion/chat-model.js?raw";
import navigationReference from "../../../../design/baseline/platform-expansion/Сотрудники и агенты.dc.html?raw";
import widgetReference from "../../../../design/baseline/Веб-чат · поля и оформление/Веб-чат · поля и оформление.dc.html?raw";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BotIcon } from "@chatballs/ui";
import { Icon } from "./icons";
import { NavigationIcon } from "../layout/NavigationIcon";
import { WidgetIcon } from "../features/integrations/appearance/WidgetIcon";

describe("shared branding against approved vectors", () => {
  it("keeps the sunset SVG byte for byte", () => {
    expect(logoSource).toBe(logoReference);
  });

  it("uses the exact outline from I.robot without blink", () => {
    const path = chatReference.match(/robot: "([^"]+)"/)?.[1];
    expect(path).toBeTruthy();
    const html = renderToStaticMarkup(<Icon name="robot" size={28} strokeWidth={2.2} />);
    expect(html).toContain(`d="${path}"`);
    expect(html).toContain('fill="none"');
    expect(html).toContain('stroke-width="2.2"');
    expect(html).not.toContain("animation");
  });

  it("uses STATS without changing the generic grid", () => {
    const path = navigationReference.match(/const STATS = "([^"]+)"/)?.[1];
    expect(path).toBeTruthy();
    expect(renderToStaticMarkup(<NavigationIcon name="stats" />)).toContain(`d="${path}"`);
    const grid = renderToStaticMarkup(<Icon name="grid" />);
    expect(grid).toContain('width="7" height="9"');
    expect(grid).toContain('width="7" height="5"');
  });

  it("retains the widget's filled baseline and its optional blink", () => {
    const body = renderToStaticMarkup(<BotIcon blink={false} />);
    const paths = [...body.matchAll(/ d="([^"]+)"/g)].map((match) => match[1]);
    expect(paths.length).toBeGreaterThan(0);
    for (const path of paths) expect(widgetReference).toContain(`d="${path}"`);
    expect(body).toContain('viewBox="0 0 48 48"');
    expect(body).not.toContain("animation");
    expect(renderToStaticMarkup(<BotIcon />)).toContain("wcBotBlink");
  });

  it("respects an uploaded widget icon and the no-icon mode", () => {
    const custom = renderToStaticMarkup(<WidgetIcon url="/uploaded-icon.svg" size={28} />);
    expect(custom).toContain('src="/uploaded-icon.svg"');
    expect(custom).not.toContain("<svg");
    expect(renderToStaticMarkup(<WidgetIcon url={null} size={28} />)).toBe("");
    const standard = renderToStaticMarkup(<WidgetIcon url="" size={28} />);
    expect(standard).toContain('viewBox="0 0 48 48"');
    expect(standard).not.toContain("animation");
  });
});
