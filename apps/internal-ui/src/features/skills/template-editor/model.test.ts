import { describe, expect, it } from "vitest";
import { changesOutside, newTemplate, updateTemplate, withExamples } from "./model";
import { diagnosticLine } from "./codeDiagnostics";
import { emptyConfiguration } from "../model";
import { displayDiagnostics, isParentError } from "./api";

describe("shared template draft and example diagnostics", () => {
  it("keeps the whole configuration for atomic save and detects changes outside this template", () => {
    const template = newTemplate();
    const baseline = { ...emptyConfiguration(), templates: [template, newTemplate()] };
    const changed = updateTemplate(baseline, { ...template, name: "Edited" });
    expect(changesOutside(changed, baseline, template.id)).toBe(false);
    expect(changesOutside({ ...changed, instruction: "Updated" }, baseline, template.id)).toBe(true);
    expect(changed.templates[1]).toBe(baseline.templates[1]);
    expect(changed.templates[0].id).toBe(template.id);
  });
  it("keeps malformed temporary JSON out of saved configuration without discarding the last data", () => {
    const template = { ...newTemplate(), examples: [{ total: 12 }] };
    expect(withExamples(template, ["{broken"]).examples).toEqual([{ total: 12 }]);
    expect(withExamples(template, ["[]"]).examples).toEqual([{ total: 12 }]);
    expect(withExamples(template, ['{"total":"два"}']).examples).toEqual([{ total: "два" }]);
  });
  it("locates repeated list keys and missing data without inspecting rendered HTML", () => {
    const source = '{\n "items": [\n  {"qty": 1},\n  {"qty": "два"}\n ],\n "discount": 10\n}';
    const error = { origin: "example", tab: "example", path: "items[1].qty", detail: "type" };
    expect(diagnosticLine(source, error)).toBe(4);
    expect(diagnosticLine(source, { ...error, path: "discount" })).toBe(6);
    expect(diagnosticLine(source, { ...error, path: "total" })).toBe(1);
  });
  it("separates parent form errors from identically named input data and hides API container paths", () => {
    const error = { origin: "configuration", tab: "schema", path: "name", detail: "Required" };
    expect(isParentError(error)).toBe(true);
    expect(isParentError({ ...error, origin: "example" })).toBe(false);
    const template = newTemplate();
    const result = displayDiagnostics([{ ...error, tab: "css", path: "templates[0]" }],
      { ...emptyConfiguration(), templates: [template] }, 0);
    expect(result[0].path).toBe("");
  });
});
