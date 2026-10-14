import { describe, expect, it } from "vitest";
import { criterionName, displayedJob, sameScale, scaleLabel } from "./presentation";
import type { QualityJob } from "./types";

describe("quality result selection", () => {
  const jobs = [
    { id: 11, state: "RUNNING", criteriaVersion: 3, revision: 2 },
    { id: 10, state: "SUCCEEDED", criteriaVersion: 2, revision: 1 },
  ] as QualityJob[];
  it("keeps the successful historical revision while a repeat runs or fails", () => {
    expect(displayedJob(jobs, null)?.criteriaVersion).toBe(2);
    expect(displayedJob([{ ...jobs[0], state: "FAILED" }, jobs[1]], null)?.id).toBe(10);
    expect(displayedJob(jobs, 11)?.id).toBe(11);
  });
  it("selects a new successful revision without replacing the preserved old one", () => {
    const completed = [{ ...jobs[0], state: "SUCCEEDED" as const }, jobs[1]];
    expect(displayedJob(completed, null)?.id).toBe(11);
    expect(displayedJob(completed, 10)?.criteriaVersion).toBe(2);
    expect(jobs[1].criteriaVersion).toBe(2);
  });
});
describe("snapshot presentation", () => {
  it("preserves typed values and nonconsecutive scales", () => {
    expect(sameScale([1, 2], ["1", "2"])).toBe(false);
    expect(scaleLabel([0, 5, 10])).toBe("0 / 5 / 10");
    expect(scaleLabel([1, 2, 3, 4, 5])).toBe("1–5");
  });
  it("uses historical descriptions for legacy criteria instead of exposing API codes", () => {
    expect(criterionName({ code: "resolution", description: "Вопрос решён", scale: [1, 2] })).toBe("Вопрос решён");
  });
});
