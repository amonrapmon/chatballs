import { describe, expect, it } from "vitest";

import { isTrustedCrmUrl } from "./model";

describe("CRM external link safety", () => {
  it("allows only DIKIDI client search on its canonical host", () => {
    expect(isTrustedCrmUrl("https://dikidi.net/ru/owner/clients/?company=123&filter=username&query=79161234567", "DIKIDI")).toBe(true);
    expect(isTrustedCrmUrl("https://dikidi.net.evil.test/ru/owner/clients/?company=123", "DIKIDI")).toBe(false);
    expect(isTrustedCrmUrl("http://dikidi.net/ru/owner/clients/?company=123", "DIKIDI")).toBe(false);
    expect(isTrustedCrmUrl("https://dikidi.net:8443/ru/owner/clients/?company=123", "DIKIDI")).toBe(false);
  });
  it("allows only the canonical YCLIENTS search path", () => {
    expect(isTrustedCrmUrl("https://yclients.ru/clients/688638/base?filters%5B0%5D%5Boperation%5D=OR", "YCLIENTS")).toBe(true);
    expect(isTrustedCrmUrl("https://yclients.ru/clients/688638/private", "YCLIENTS")).toBe(false);
    expect(isTrustedCrmUrl("https://yclients.ru/clients/688638/base", "DIKIDI")).toBe(false);
  });
});
