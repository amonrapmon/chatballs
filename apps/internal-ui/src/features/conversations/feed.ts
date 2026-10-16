import type { ApiMessage } from "./apiTypes";
import type { ApiComment } from "./commentApi";
import { conversationTimeline, type TimelineRow } from "./timeline";

// Лента диалога собирается из двух независимых окон — сообщений и внутренних
// комментариев. У них разные идентификаторы и курсоры, общий у них только
// момент создания: по нему строки и встают в один ряд.

export type FeedRow =
  | ({ kind: "message"; key: string; createdAt: string } & TimelineRow)
  | { kind: "comment"; key: string; createdAt: string; comment: ApiComment };

export type FeedStream<T> = { items: readonly T[]; hasOlder: boolean };

const timeOf = (iso: string) => new Date(iso).getTime();

function floorOf(stream: FeedStream<{ createdAt: string }>): number | null {
  return stream.hasOlder && stream.items.length > 0 ? timeOf(stream.items[0].createdAt) : null;
}

/** Какое окно догружать при прокрутке вверх: то, что держит границу ленты. */
export function olderStream(
  messages: FeedStream<ApiMessage>,
  comments: FeedStream<ApiComment>,
): "messages" | "comments" | null {
  const messageFloor = floorOf(messages);
  const commentFloor = floorOf(comments);
  if (messageFloor === null && commentFloor === null) return null;
  if (commentFloor === null) return "messages";
  if (messageFloor === null) return "comments";
  return messageFloor >= commentFloor ? "messages" : "comments";
}

/** Раньше границы одно из окон ещё не догружено: строки второго встали бы там
 *  с пропусками, поэтому до догрузки они не показываются. */
export function conversationFeed(
  messages: FeedStream<ApiMessage>,
  comments: FeedStream<ApiComment>,
): FeedRow[] {
  const floor = Math.max(floorOf(messages) ?? -Infinity, floorOf(comments) ?? -Infinity);
  const visible = (row: FeedRow) => timeOf(row.createdAt) >= floor;
  const messageRows = conversationTimeline(messages.items)
    .map((row): FeedRow => ({ kind: "message", key: `m${row.message.id}`, createdAt: row.message.createdAt, ...row }))
    .filter(visible);
  const commentRows = comments.items
    .map((comment): FeedRow => ({ kind: "comment", key: `c${comment.id}`, createdAt: comment.createdAt, comment }))
    .filter(visible);

  // Слияние сохраняет порядок внутри каждого окна; при равном времени реплика
  // клиенту идёт раньше комментария к ней.
  const rows: FeedRow[] = [];
  let next = 0;
  for (const row of messageRows) {
    while (next < commentRows.length && timeOf(commentRows[next].createdAt) < timeOf(row.createdAt)) rows.push(commentRows[next++]);
    rows.push(row);
  }
  return rows.concat(commentRows.slice(next));
}

export function isOwnFeedRow(row: FeedRow, viewerId: number | null): boolean {
  if (viewerId === null) return false;
  return row.kind === "comment"
    ? row.comment.author.id === viewerId
    : row.message.author === "OPERATOR" && row.message.authorUserId === viewerId;
}
