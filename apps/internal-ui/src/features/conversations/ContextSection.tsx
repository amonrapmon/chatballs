import type { ReactNode } from "react";

// Строительный блок секции правой панели (ClientContext, HistoryContext).
// Класс sales-* — design baseline, переиспользуется без переименования
// (SPEC §8.4 layout без изменений).
export function ContextSection({ title, action, headerExtra, className = "", children }: {
  title: string;
  action?: string;
  headerExtra?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`sales-context-section ${className}`.trim()}>
      <div className="sales-context-section-head">
        <h4>{title}</h4>
        {headerExtra}
        {action && <button>{action}</button>}
      </div>
      {children}
    </section>
  );
}
