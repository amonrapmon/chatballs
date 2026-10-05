import { Icon } from "../../../shared/icons";
import { fieldIcons, type FieldType } from "./model";

// The number and boolean glyphs come from W1; other glyphs already exist in Icon.
export function FieldTypeIcon({ type }: { type: FieldType }) {
  if (type !== "number" && type !== "boolean") return <Icon name={fieldIcons[type]} size={13} />;
  return <svg viewBox="0 0 24 24" width={13} height={13} fill="none" stroke="currentColor"
    strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={type === "number" ? "M4 9h16M4 15h16M10 3 8 21M16 3l-2 18"
      : "M8 7h8a5 5 0 0 1 0 10H8A5 5 0 0 1 8 7zM16 12a0 0 0 0 1 0 0M16 10a2 2 0 1 1 0 4 2 2 0 0 1 0-4z"} />
  </svg>;
}
