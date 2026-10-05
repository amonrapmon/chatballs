import { t } from "./i18n";
import { widgetClasses as classes } from "./widgetClasses";

export function StartChatFooter({ accent, starting, onAccept }: { accent: string; starting: boolean; onAccept: () => void }) {
  return <div className={classes.startFooter} style={{ "--cb-accent": accent } as React.CSSProperties}><button onClick={onAccept} disabled={starting} className={classes.startButton}>{starting ? t("chat.starting") : t("chat.accept_and_start")}</button></div>;
}

