import { describe, expect, it } from "vitest";

import { displayProvider, displayProviderKey } from "./providers";

describe("API Connector display platform", () => {
  it("uses native messenger icons without changing the connector transport", () => {
    expect(displayProvider("API_CONNECTOR", "green_api_telegram")).toBe("TELEGRAM");
    expect(displayProviderKey("API_CONNECTOR", "green_api_telegram")).toBe("TG");
    expect(displayProviderKey("API_CONNECTOR", "green_api_max")).toBe("MAX");
    expect(displayProviderKey("API_CONNECTOR", "green_api_vk")).toBe("VK");
  });

  it("does not mislabel unknown sources as the web widget", () => {
    expect(displayProviderKey("API_CONNECTOR", "custom_adapter")).toBe("API_CONNECTOR");
    expect(displayProviderKey("API_CONNECTOR")).toBe("API_CONNECTOR");
    expect(displayProviderKey(null)).toBe("API_CONNECTOR");
  });

  it("keeps native platform and respects a backend display override", () => {
    expect(displayProviderKey("WEB")).toBe("WEB");
    expect(displayProviderKey("TELEGRAM")).toBe("TG");
    expect(displayProviderKey("API_CONNECTOR", undefined, "MAX")).toBe("MAX");
  });
});
