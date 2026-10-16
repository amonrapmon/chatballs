import type { Configuration, SkillTemplate } from "../model";

export function newTemplate(): SkillTemplate {
  return { id: crypto.randomUUID(), name: "", purpose: "", schema: { type: "object", properties: {} },
    html: "", css: "", text: "", examples: [{}] };
}
export function updateTemplate(configuration: Configuration, template: SkillTemplate): Configuration {
  return { ...configuration, templates: configuration.templates.map((item) => item.id === template.id ? template : item) };
}
export function changesOutside(configuration: Configuration, baseline: Configuration, templateId: string) {
  const without = (value: Configuration) => ({ ...value, templates: value.templates.filter((item) => item.id !== templateId) });
  return JSON.stringify(without(configuration)) !== JSON.stringify(without(baseline));
}
export function withExamples(template: SkillTemplate, inputs: string[]): SkillTemplate {
  return { ...template, examples: inputs.map((input, index) => {
    try {
      const data = JSON.parse(input);
      return data && typeof data === "object" && !Array.isArray(data) ? data : template.examples[index] ?? {};
    } catch { return template.examples[index] ?? {}; }
  }) };
}
