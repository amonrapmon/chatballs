import { BotIcon } from "@chatballs/ui";

export function WidgetIcon({ url, size }: { url: string | null; size: number }) {
  if (url === null) return null;
  return url ? <img src={url} alt="" width={size} height={size} style={{ objectFit: "contain" }} />
    : <BotIcon size={size} blink={false} />;
}
