import type { ReactNode } from "react";

import { Icon, LogoSpinner } from "../../shared/icons";

/** Кадры D, E: редактор заменён карточкой-сообщением. */
export function ComposerLocked({ title, text, loading = false, icon = true, action }: { title?: string; text?: string; loading?: boolean; icon?: boolean; action?: ReactNode }) {
  if (loading) return <div className="sales-composer"><div className="composer-locked is-loading"><LogoSpinner size={22} /></div></div>;
  return (
    <div className="sales-composer"><div className="composer-locked">
      {icon && <span><Icon name="lock" size={19} /></span>}
      <div><strong>{title}</strong>{text && <p>{text}</p>}</div>
      {action}
    </div></div>
  );
}
