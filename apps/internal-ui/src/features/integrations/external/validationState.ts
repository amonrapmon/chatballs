import type { FieldErrors, ServerDraft } from "./types";

export type ValidationState = { changed: string[]; blurred: string[]; submitted: boolean };
export const initialValidationState: ValidationState = { changed: [], blurred: [], submitted: false };

export function validationAfterChange(state: ValidationState, previous: ServerDraft, next: ServerDraft): ValidationState {
  const fields = new Set(state.changed);
  if (previous.name !== next.name) fields.add("name");
  for (const key of Object.keys(next.externalServer) as Array<keyof ServerDraft["externalServer"]>) {
    if (JSON.stringify(previous.externalServer[key]) !== JSON.stringify(next.externalServer[key])) fields.add(key);
  }
  return { ...state, changed: [...fields] };
}

export function validationAfterBlur(state: ValidationState, field: string): ValidationState {
  if (!state.changed.includes(field) || state.blurred.includes(field)) return state;
  return { ...state, blurred: [...state.blurred, field] };
}

export function visibleValidationErrors(errors: FieldErrors, state: ValidationState): FieldErrors {
  return Object.fromEntries(Object.entries(errors).filter(([field]) => state.submitted || state.blurred.includes(field)));
}
