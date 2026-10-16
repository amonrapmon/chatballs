import type { RatingRequest } from "./api";
import { openRating } from "./handoff";
import { Stars } from "./Stars";
import { t } from "../i18n";
import { requestText } from "./requestText";
import "./rating.css";

export function RatingRequestCard({ request }: { request: RatingRequest }) {
  return <section className="widget-rating-request"><h3>{requestText(request.text).heading}</h3><p>{t("ratings.open_form")}</p>
    <Stars scale={request.scale} value={0} onSelect={value => openRating(request, value)} />
    <div className="rating-endpoints"><span>{request.scale[0]?.label}</span><span>{request.scale.at(-1)?.label}</span></div>
  </section>;
}
