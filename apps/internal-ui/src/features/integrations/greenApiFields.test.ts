import { describe, expect, it } from "vitest";
import { GREEN_API_FIELDS, greenApiReady, isGreenApiService } from "./greenApiFields";

const ready = {
  idInstance: "7103123456", apiTokenInstance: "token-" + "x".repeat(24),
  apiUrl: "https://7103.api.green-api.com/",
  mediaUrl: "https://7103.media.green-api.com/"
};

describe("Green API messenger schema", () => {
  it("uses the installed native control registry and keeps credentials secret", () => {
    expect(GREEN_API_FIELDS.map(field => field.control)).toEqual([
      "text@1", "secret@1", "url@1", "url@1"
    ]);
    expect(GREEN_API_FIELDS.find(field => field.name === "apiTokenInstance")?.secret).toBe(true);
    expect(GREEN_API_FIELDS.every(field => field.required)).toBe(true);
  });
  it("validates both real platforms, but not an arbitrary connector", () => {
    expect(isGreenApiService("green_api_telegram")).toBe(true);
    expect(isGreenApiService("green_api_max")).toBe(true);
    expect(isGreenApiService("green_api_whatsapp")).toBe(false);
    expect(greenApiReady(ready)).toBe(true);
    expect(greenApiReady({ ...ready, apiUrl: "https://127.0.0.1/" })).toBe(false);
    expect(greenApiReady({ ...ready, idInstance: "nope" })).toBe(false);
    expect(greenApiReady({ ...ready, apiTokenInstance: "" })).toBe(false);
  });
});
