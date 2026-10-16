import { useState } from "react";
import { t, fmt } from "../../i18n";
import { FormField, TextAreaField, SelectField } from "../../shared/form-controls";
import { validateConfiguration, type Configuration } from "./model";
import { isParentError, type Diagnostic } from "./template-editor/api";
export function SkillFields({
  draft,
  change,
  attempted,
  busy,
  creating,
  basis,
  changeBasis,
  serverErrors = [],
}: {
  draft: Configuration;
  change: (draft: Configuration) => void;
  attempted: boolean;
  busy: boolean;
  creating: boolean;
  basis: string;
  changeBasis: (basis: string) => void;
  serverErrors?: Diagnostic[];
}) {
  const [touched, setTouched] = useState<string[]>([]);
  const errors = { ...Object.fromEntries(serverErrors.filter(isParentError).map((error) => [error.path, error.detail])),
    ...validateConfiguration(draft) };
  const update = (key: "name" | "description" | "instruction", value: string) => {
    setTouched((items) => [...items, key]);
    change({ ...draft, [key]: value });
  };
  return (
    <section className="skill-panel skill-fields">
      <h3>{t("skills.main")}</h3>
      {creating && (
        <SelectField
          label={t("skills.basis")}
          value={basis}
          onChange={changeBasis}
          disabled={busy}
          options={[
            ["", t("skills.blank")],
            ["orders", t("skills.orders")],
          ]}
        />
      )}
      <div>
        <FormField
          label={t("skills.name")}
          value={draft.name}
          disabled={busy}
          onChange={(value) => update("name", value)}
          error={attempted || touched.includes("name") ? errors.name : undefined}
        />
        <small className="skill-counter">
          {fmt.number(Array.from(draft.name).length)} / {fmt.number(60)}
        </small>
      </div>
      {(["description", "instruction"] as const).map((key) => (
        <div
          key={key}
          className={`skill-field-${key} ${(attempted || touched.includes(key)) && errors[key] ? "is-invalid" : ""}`}>
          <TextAreaField
            label={t(key === "description" ? "skills.description" : "skills.instruction")}
            value={draft[key]}
            disabled={busy}
            onChange={(value) => update(key, value)}
          />
          {key === "description" && (
            <small className="skill-counter">
              {fmt.number(Array.from(draft.description).length)} / {fmt.number(200)}
            </small>
          )}
          {(attempted || touched.includes(key)) && errors[key] && (
            <small className="form-field-error" role="alert">
              {errors[key]}
            </small>
          )}
          <small>{t(key === "description" ? "skills.description_hint" : "skills.instruction_hint")}</small>
        </div>
      ))}
    </section>
  );
}
