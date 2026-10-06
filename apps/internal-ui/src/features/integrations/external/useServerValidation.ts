import { useState } from "react";
import type { FieldErrors, ServerDraft } from "./types";
import { initialValidationState, validationAfterBlur, validationAfterChange, visibleValidationErrors } from "./validationState";

export function useServerValidation() {
  const [state, setState] = useState(initialValidationState);
  return {
    submitted: state.submitted,
    showField: (field: string) => state.submitted || state.blurred.includes(field),
    visibleErrors: (errors: FieldErrors) => visibleValidationErrors(errors, state),
    change: (previous: ServerDraft, next: ServerDraft) => setState((current) => validationAfterChange(current, previous, next)),
    blur: (field: string) => setState((current) => validationAfterBlur(current, field)),
    submit: () => setState((current) => ({ ...current, submitted: true })),
    reset: () => setState(initialValidationState),
  };
}
