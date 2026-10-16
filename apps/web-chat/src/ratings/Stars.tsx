import { fmt } from "../i18n";
import type { RatingChoice } from "./api";

export function Stars({ scale, value, onSelect, disabled = false, small = false }: {
  scale: RatingChoice[]; value: number; onSelect?: (value: number) => void; disabled?: boolean; small?: boolean;
}) {
  return <div className={`rating-stars ${small ? "is-small" : ""}`} role={onSelect ? "radiogroup" : undefined}>
    {scale.map(choice => {
      const star = <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.8l2.8 5.8 6.3.9-4.6 4.4 1.1 6.3L12 17.2l-5.6 3 1.1-6.3-4.6-4.4 6.3-.9z" /></svg>;
      const title = `${fmt.number(choice.value)} — ${choice.label}`;
      const className = `${choice.value <= value ? "is-filled" : ""} ${choice.value === value ? "is-picked" : ""}`;
      return onSelect ? <button type="button" role="radio" key={choice.value} title={title} aria-label={title} aria-checked={value === choice.value}
        className={className} disabled={disabled} onClick={() => onSelect(choice.value)}>{star}</button>
        : <span key={choice.value} title={title} className={className}>{star}</span>;
    })}
  </div>;
}
