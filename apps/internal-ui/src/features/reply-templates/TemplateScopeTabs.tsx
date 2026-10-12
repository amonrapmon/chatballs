import { fmt, t } from "../../i18n";
import { Icon } from "../../shared/icons";
import type { TemplateScope } from "./api";
import "./scope-tabs.css";

// Переключатель области шаблонов на общем стиле `.segmented`: вкладки
// библиотеки со счётчиками (N3), «Где хранить» в окне шаблона (N5, N9) и
// «Все · Личные · Общие» в выборе из редактора (T1).

export function TemplateScopeTabs({ value, onChange, all = false, singular = false, sharedLocked = false, disabled = false, counts }: {
  value: TemplateScope | "";
  onChange: (value: TemplateScope | "") => void;
  /** Пункт «Все» перед областями — только в выборе из редактора. */
  all?: boolean;
  /** «Личный / Общий» вместо «Личные / Общие» и подсказки о видимости. */
  singular?: boolean;
  /** Нет права на общие шаблоны: пункт недоступен, с замком и причиной. */
  sharedLocked?: boolean;
  disabled?: boolean;
  counts?: Record<TemplateScope, number>;
}) {
  const items: Array<{ key: TemplateScope | ""; label: string; title?: string; locked?: boolean }> = [
    ...(all ? [{ key: "" as const, label: t("templates.all") }] : []),
    {
      key: "PERSONAL",
      label: t(singular ? "templates.personal_one" : "templates.personal"),
      title: singular ? t("templates.personal_title") : undefined,
    },
    {
      key: "SHARED",
      label: t(singular ? "templates.shared_one" : "templates.shared"),
      title: sharedLocked ? t("templates.permission_needed") : singular ? t("templates.shared_title") : undefined,
      locked: sharedLocked,
    },
  ];
  return (
    <div className="segmented template-scope-tabs" role="group" aria-label={t("templates.scope")}>
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          className={item.key === value ? "active" : ""}
          aria-pressed={item.key === value}
          disabled={disabled || item.locked}
          title={item.title}
          onClick={() => onChange(item.key)}
        >
          {item.locked && <Icon name="lock" size={12} strokeWidth={2} />}
          {item.label}
          {counts && item.key && <small>{fmt.number(counts[item.key])}</small>}
        </button>
      ))}
    </div>
  );
}
