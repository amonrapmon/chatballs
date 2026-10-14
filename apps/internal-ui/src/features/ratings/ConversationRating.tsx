import { useEffect, useState } from "react";
import { fmt, t } from "../../i18n";
import { fetchRatingCard, type RatingCardData, type RatingResult } from "./api";
import "./card.css";

export function ConversationRating({ conversationId }: { conversationId: number }) {
  const [data, setData] = useState<RatingCardData | null>(null);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try { const next = await fetchRatingCard(conversationId); if (active) setData(next); }
      catch { if (active) setData(null); }
      finally { if (active) timer = setTimeout(refresh, 10000); }
    }
    setData(null); void refresh();
    return () => { active = false; clearTimeout(timer); };
  }, [conversationId]);
  if (!data) return null;
  if (data.results.length) return <>{data.results.map(result => <RatingResultCard key={result.id} result={result} />)}</>;
  return <section className="conversation-rating">
    <header><h4>{t("ratings.card_title")}</h4></header>
    <p className="conversation-rating-empty">{!data.request && !data.enabled ? t("ratings.not_requested") : <>{t("ratings.no_result")}{data.request?.sentAt && ` ${t("ratings.sent_at", { when: fmt.shortDateTime(data.request.sentAt) })}`}</>}</p>
  </section>;
}

function RatingResultCard({ result }: { result: RatingResult }) {
  const minimum = Math.min(...result.scale.map(choice => choice.value));
  const maximum = Math.max(...result.scale.map(choice => choice.value));
  const label = result.scale.find(choice => choice.value === result.value)?.label;
  return <section className="conversation-rating">
    <header><h4>{t("ratings.card_title")}</h4><small>{fmt.shortDateTime(result.receivedAt)}</small></header>
    <div className="conversation-rating-value"><strong>{fmt.number(result.value)}</strong><span>{t("ratings.out_of", { maximum: fmt.number(maximum) })}</span><b>{label}</b></div>
    <div className="conversation-rating-scale">{result.scale.map(choice => <span key={choice.value} className={choice.value === result.value ? "is-selected" : ""} title={`${fmt.number(choice.value)} — ${choice.label}`}>{fmt.number(choice.value)}</span>)}</div>
    <small>{t("ratings.snapshot_scale", { minimum: fmt.number(minimum), maximum: fmt.number(maximum) })}</small>
    {result.comment && <p className="conversation-rating-comment">{result.comment}</p>}
    <div className="conversation-rating-responders"><span>{t("ratings.responders")}</span><div>{result.responders.map(person => <span key={person.id}>
      {person.avatarUrl ? <img src={person.avatarUrl} alt="" /> : <i>{person.name.split(/\s+/).map(part => part[0]).slice(0, 2).join("")}</i>}{person.name}
    </span>)}</div></div>
  </section>;
}
