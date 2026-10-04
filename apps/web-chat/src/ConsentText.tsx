import type { WebConfig } from "./api";
import { t } from "./i18n";
import { widgetClasses as classes } from "./widgetClasses";

// Подпись редакции: в строке — со строчной, отдельной строкой — с прописной.
const REVISION = {
  screen: { inline: "chat.consent_revision", line: "chat.consent_revision_line" },
  form: { inline: "pre_chat.consent_revision", line: "pre_chat.consent_revision_line" },
} as const;

// Перенос, абзац или список: текст уже не в одну строку.
const MULTILINE = /<(br|p|ul|ol|li)\b/i;

/**
 * Текст согласия с подписью редакции. Разметку очищает сервер по белому списку
 * (SPEC-0020 R-14–R-15) — виджет выводит её как есть и своих правил не заводит.
 */
export function ConsentText({ consent, place, className }: {
  consent: WebConfig["consent"];
  place: keyof typeof REVISION;
  className?: string;
}) {
  const html = consent?.text ?? "";
  const version = consent?.version ?? "";
  const multiline = MULTILINE.test(html);
  return (
    <div className={className ? `${classes.consent} ${className}` : classes.consent}>
      {multiline
        ? <><div dangerouslySetInnerHTML={{ __html: html }} /><div className={classes.consentRevision}>{t(REVISION[place].line, { version })}</div></>
        : <><span dangerouslySetInnerHTML={{ __html: html }} /> · {t(REVISION[place].inline, { version })}</>}
    </div>
  );
}
