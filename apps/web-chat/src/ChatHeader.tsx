import { BotIcon } from "./BotIcon";
import { t } from "./i18n";
import { widgetClasses as classes } from "./widgetClasses";

export function ChatHeader({ accent, icon, title, expanded, canExpand, onToggleExpand, onClose }: { accent: string; icon?: string | null; title: string; expanded: boolean; canExpand: boolean; onToggleExpand: () => void; onClose: () => void }) {
  return (
    <div className={classes.header} style={{ "--cb-accent": accent } as React.CSSProperties}>
      {icon !== null && (icon ? <img className={classes.headerIcon} src={icon} alt="" /> : <span className={classes.headerIcon}><BotIcon size={34} /></span>)}
      <div className={classes.headerTitle}>{title}</div>
      {canExpand && <button className={`wc-icon-button ${classes.headerButton}`} onClick={onToggleExpand} aria-label={expanded ? t("chat.shrink_panel") : t("chat.expand_panel")}>
        {expanded
          ? <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round"><path d="M9 3v4a2 2 0 0 1-2 2H3" /><path d="M15 3v4a2 2 0 0 0 2 2h4" /><path d="M9 21v-4a2 2 0 0 0-2-2H3" /><path d="M15 21v-4a2 2 0 0 1 2-2h4" /></svg>
          : <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3" /><path d="M16 3h3a2 2 0 0 1 2 2v3" /><path d="M8 21H5a2 2 0 0 1-2-2v-3" /><path d="M16 21h3a2 2 0 0 0 2-2v-3" /></svg>}
      </button>}
      <button className={`wc-icon-button ${classes.headerButton}`} onClick={onClose} aria-label={t("chat.collapse")}>
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12" /></svg>
      </button>
    </div>
  );
}

