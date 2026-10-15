import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CrmBrandIcon } from "./CrmBrandIcon";

describe("CRM branded SVG icons", () => {
  it("renders a black Y on the official yellow circle", () => {
    const html = renderToStaticMarkup(<CrmBrandIcon provider="YCLIENTS" />);
    expect(html).toContain('fill="#FFCB00"');
    expect(html).toContain('stroke="#000000"');
    expect(html).toContain('aria-hidden="true"');
  });

  it("renders a white D on the navy circle", () => {
    const html = renderToStaticMarkup(<CrmBrandIcon provider="DIKIDI" />);
    expect(html).toContain('fill="#182B5F"');
    expect(html).toContain('stroke="#FFFFFF"');
    expect(html).toContain('viewBox="0 0 20 20"');
  });
});
