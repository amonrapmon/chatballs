/** Строка под редактором (кадры C3–C4): причина ошибки или напоминание, кому уйдёт текст. */
export function ComposerFoot({ tone, text, actionLabel, onAction }: { tone: "error" | "warning"; text: string; actionLabel?: string; onAction?: () => void }) {
  return (
    <div className={`composer-foot is-${tone}`}>
      <i />
      <span>{text}{actionLabel && <> <button className="link" type="button" onClick={onAction}>{actionLabel}</button></>}</span>
    </div>
  );
}
