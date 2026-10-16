import { t } from "../../../i18n";
import { Button } from "../../../shared/ui-controls";
import type { SkillTemplate } from "../model";
import type { Diagnostic } from "./api";
import { CodeEditor } from "./CodeEditor";

export function TemplateExamples({ template, inputs, selected, select, change, errors, disabled }: {
  template: SkillTemplate; inputs: string[]; selected: number; select: (index: number) => void;
  change: (inputs: string[]) => void; errors: Diagnostic[]; disabled: boolean;
}) {
  const label = (index: number) => template.exampleNames?.[index]
    || t("skill_templates.example_number", { number: index + 1 });
  return <section className={`template-panel template-examples ${errors.length ? "is-invalid" : ""}`}>
    <header><strong>{t("skill_templates.example")}</strong>
      {inputs.map((_, index) => <button key={index} className={`template-sample ${selected === index ? "is-active" : ""}`}
        onClick={() => select(index)}>{label(index)}</button>)}
      <Button variant="secondary" icon="plus" disabled={disabled || inputs.length >= 8} title={t("skill_templates.add_example")}
        aria-label={t("skill_templates.add_example")} onClick={() => { change([...inputs, "{}"]); select(inputs.length); }} />
    </header>
    <CodeEditor key={selected} value={inputs[selected] ?? "{}"} language="example" label={t("skill_templates.example")}
      change={(value) => change(inputs.map((item, index) => index === selected ? value : item))} errors={errors} disabled={disabled} />
  </section>;
}
