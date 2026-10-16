import type { useRating } from "./useRating";
import { Stars } from "./Stars";
import { fmt, t } from "../i18n";

export function RatingOutcome({ rating }: { rating: ReturnType<typeof useRating> }) {
  const expired = rating.state === "expired";
  const repeat = rating.state === "rated";
  const neutral = expired || repeat;
  const result = rating.result;
  return <section className={`rating-outcome ${neutral ? "is-neutral" : ""}`}>
    <span className="rating-outcome-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d={expired ? "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM12 6v6l4 2" : "M20 6 9 17l-5-5"} /></svg></span>
    <h1>{t(expired ? "ratings.expired_title" : repeat ? "ratings.rated_title" : "ratings.thanks_title")}</h1>
    <p>{repeat && result ? t("ratings.saved_at", { when: fmt.shortDateTime(result.receivedAt) }) : t(expired ? "ratings.expired_body" : "ratings.thanks_body")}</p>
    {!expired && result && rating.question && <><Stars scale={rating.question.scale} value={result.value} small /><small>{rating.question.scale.find(choice => choice.value === result.value)?.label}</small></>}
    {expired && <a className="link rating-site-link" href={rating.presentation?.siteUrl || "/"} rel="noreferrer">{t("ratings.go_to_site")}</a>}
  </section>;
}
