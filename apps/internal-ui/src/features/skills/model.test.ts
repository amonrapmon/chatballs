import { describe, expect, it } from "vitest";
import { emptyConfiguration, requestFor, validateConfiguration } from "./model";

describe("skill configuration", () => {
  const valid = () => ({
    ...emptyConfiguration(),
    name: "Name",
    description: "When needed",
    instruction: "Ask for details\n",
  });
  it("validates required values and Unicode limits without requiring templates", () => {
    expect(validateConfiguration(valid())).toEqual({});
    expect(Object.keys(validateConfiguration(emptyConfiguration())).sort()).toEqual([
      "description",
      "instruction",
      "name",
    ]);
    expect(validateConfiguration({ ...valid(), name: "😀".repeat(60) })).toEqual({});
    expect(
      validateConfiguration({
        ...valid(),
        name: "😀".repeat(61),
        description: "x".repeat(201),
        instruction: "x".repeat(32769),
      }),
    ).toHaveProperty("name");
    expect(validateConfiguration({ ...valid(), instruction: " \n " })).toHaveProperty("instruction");
  });
  it("retries an identical atomic body/key and starts a new action after edits or a refreshed revision", () => {
    const config = valid();
    const request = requestFor(config, 7, null);
    expect(requestFor(valid(), 7, request)).toBe(request);
    config.name = "Changed";
    expect(request.configuration.name).toBe("Name");
    expect(requestFor(config, 7, request).requestId).not.toBe(request.requestId);
    expect(requestFor(valid(), 8, request).requestId).not.toBe(request.requestId);
    expect(requestFor(valid(), undefined, null)).not.toHaveProperty("expectedRevision");
  });
});
