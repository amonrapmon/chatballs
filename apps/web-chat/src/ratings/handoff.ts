import type { RatingPresentation, RatingRequest } from "./api";

const KEY = "chatballs-rating";
export type RatingHandoff = { credential: string; value: number; presentation: RatingPresentation };

export function readRatingHandoff(): RatingHandoff | null {
  try { return JSON.parse(sessionStorage.getItem(KEY) || "null") as RatingHandoff | null; }
  catch { return null; }
}

export function openRating(request: RatingRequest, value: number) {
  const siteUrl = request.presentation.siteUrl || new URL(document.referrer || location.origin).origin;
  // A new same-origin tab receives a copy of sessionStorage. No credential in
  // path, query, fragment, referrer, cookies, browser history or localStorage.
  sessionStorage.setItem(KEY, JSON.stringify({ credential: request.credential, value, presentation: { ...request.presentation, siteUrl } }));
  const tab = window.open("/chat/rating.html", "_blank");
  if (tab) tab.opener = null;
  sessionStorage.removeItem(KEY);
}
