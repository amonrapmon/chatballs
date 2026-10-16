import { api } from "../../api/client";

export type RatingChoice = { value: number; label: string };
export type RatingSettings = {
  enabled: boolean; scale: RatingChoice[]; text: string; delaySeconds: number;
  updatedAt: string | null; updatedBy: string;
  defaults?: { scale: RatingChoice[]; text: string; delaySeconds: number };
};
export type RatingResult = {
  id: number; value: number; scale: RatingChoice[]; comment: string; receivedAt: string;
  responders: { id: number; name: string; avatarUrl: string | null }[];
};
export type RatingCardData = { results: RatingResult[]; request: { sentAt: string | null } | null; enabled: boolean };

export const fetchRatingSettings = () => api<RatingSettings>("/api/v1/ratings/settings/");
export const saveRatingSettings = (value: Pick<RatingSettings, "enabled" | "scale" | "text" | "delaySeconds">) =>
  api<RatingSettings>("/api/v1/ratings/settings/", { method: "PATCH", body: JSON.stringify(value) });
export const fetchRatingCard = (id: number) => api<RatingCardData>(`/api/v1/ratings/conversations/${id}/`);
