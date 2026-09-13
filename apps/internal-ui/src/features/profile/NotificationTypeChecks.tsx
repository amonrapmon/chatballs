import { Icon } from "../../shared/icons";

// Галочки типов событий. Один и тот же список у каждого транспорта: вопрос
// «о чём меня звать» один, и выглядеть он обязан одинаково — что у бота в
// мессенджере, что у браузера.

export type NotificationTypeOption = { code: string; label: string };

export function NotificationTypeChecks({
  options,
  selected,
  onToggle,
}: {
  options: NotificationTypeOption[];
  selected: string[];
  onToggle: (code: string) => void;
}) {
  // Список приходит из ответа сервера: недостающее поле не повод уронить
  // экран, на котором эта строка — лишь часть карточки.
  if (!options || options.length === 0) return null;
  return (
    <div className="profile-notifications-types">
      {options.map((option) => {
        const on = selected.includes(option.code);
        return (
          <label key={option.code}>
            <input type="checkbox" checked={on} onChange={() => onToggle(option.code)} />
            <span className={`profile-check ${on ? "is-on" : ""}`}>
              {on && <Icon name="check" size={11} strokeWidth={3} />}
            </span>
            {option.label}
          </label>
        );
      })}
    </div>
  );
}
