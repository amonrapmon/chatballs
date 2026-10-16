import type { useRating } from "./useRating";
import { Stars } from "./Stars";
import { fmt, t } from "../i18n";
import { requestText } from "./requestText";

export function RatingForm({ rating }: { rating: ReturnType<typeof useRating> }) {
  const { question, value, comment, busy, failed } = rating;
  const label = question?.scale.find(choice => choice.value === value)?.label;
  // The company's editable request supplies the question and its continuation.
  const { heading, body } = requestText(question?.text || "");
  return <>
    {question && <section className="rating-question">
      <small>{t("ratings.conversation_date", { when: fmt.dayMonthLong(question.presentation.conversationDate) })}</small>
      <h1>{heading}</h1>{body && <p>{body}</p>}
      <Stars scale={question.scale} value={value} onSelect={rating.setValue} disabled={busy} />
      <div className="rating-endpoints"><span>{question.scale[0]?.label}</span><span>{question.scale.at(-1)?.label}</span></div>
      <div className={`rating-pick ${value ? "is-selected" : ""}`}>{value ? t("ratings.selected", { label: label || "", value: fmt.number(value), maximum: fmt.number(question.scale.length) }) : t("ratings.pick")}</div>
    </section>}
    {question && value > 0 && <label className="rating-comment"><span>{t(value >= 4 ? "ratings.ask_positive" : "ratings.ask_improve")} <small>· {t("ratings.optional")}</small></span>
      <textarea value={comment} disabled={busy} maxLength={question.commentMaxLength} placeholder={t("ratings.comment_placeholder")} onChange={event => rating.setComment(event.target.value)} />
      <small>{t("ratings.comment_hint", { organization: rating.presentation?.name || "" })}</small>
    </label>}
    {failed && <p className="rating-send-error" role="alert"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 8v4M12 16v.01" /></svg>{t("ratings.send_error")}</p>}
    <div className="rating-submit"><button type="button" disabled={busy || (!value && Boolean(question))} onClick={() => void rating.submit()}>{t(failed ? "ratings.retry" : "ratings.submit")}</button>
      <small>{t(value ? "ratings.immutable" : "ratings.choose_range")}</small></div>
  </>;
}
