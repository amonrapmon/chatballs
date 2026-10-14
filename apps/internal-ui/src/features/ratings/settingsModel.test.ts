import { describe, expect, it } from "vitest";
import type { RatingSettings } from "./api";
import { ratingSettingsDraft, ratingSettingsInput } from "./settingsModel";

const defaults = {
  scale: Array.from({ length: 5 }, (_, index) => ({ value: index + 1, label: String(index + 1) })),
  text: "Customer question", delaySeconds: 600,
};
const empty: RatingSettings = {
  enabled: false, scale: [], text: "", delaySeconds: 0, updatedAt: null, updatedBy: "", defaults,
};

describe("rating settings form", () => {
  it("prepares an editable draft without enabling ratings or mutating the saved policy", () => {
    const draft = ratingSettingsDraft(empty);
    expect(draft.enabled).toBe(false);
    expect(ratingSettingsInput({ ...draft, enabled: true }, "10")).toMatchObject({
      invalidScale: false, error: "", value: { ...defaults, enabled: true },
    });
    draft.scale[0].label = "Custom label";
    expect(empty.scale).toEqual([]);
    expect(defaults.scale[0].label).toBe("1");
  });

  it("preserves configured values including immediate delivery instead of applying defaults", () => {
    const saved = { ...empty, scale: defaults.scale, text: "Custom question" };
    expect(ratingSettingsDraft(saved)).toMatchObject({ text: saved.text, delaySeconds: 0 });
  });

  it("validates the customer question and every scale label before sending", () => {
    const draft = { ...ratingSettingsDraft(empty), enabled: true };
    expect(ratingSettingsInput({ ...draft, text: " " }, "10").error).not.toBe("");
    const scale = draft.scale.map(choice => ({ ...choice, label: choice.value === 5 ? " " : choice.label }));
    expect(ratingSettingsInput({ ...draft, scale }, "10").invalidScale).toBe(true);
  });

  it("allows disabling an unconfigured policy and does not send blank scale choices", () => {
    const draft = ratingSettingsDraft({ ...empty, defaults: undefined });
    expect(ratingSettingsInput(draft, "0")).toMatchObject({
      invalidScale: false, error: "", value: { enabled: false, scale: [], text: "", delaySeconds: 0 },
    });
  });

  it("sends integral seconds and rejects empty, out of range and subsecond delays", () => {
    const draft = ratingSettingsDraft(empty);
    for (const [minutes, delaySeconds] of [["0", 0], ["1.5", 90], ["0.35", 21], ["10080", 604800]] as const) {
      expect(ratingSettingsInput(draft, minutes)).toMatchObject({ error: "", value: { delaySeconds } });
    }
    for (const minutes of ["", " ", "-1", "10081", "invalid", "0.01"]) {
      expect(ratingSettingsInput(draft, minutes).error).not.toBe("");
    }
  });
});
