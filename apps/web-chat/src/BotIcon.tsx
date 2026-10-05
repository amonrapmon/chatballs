import { BotIcon } from "@chatballs/ui";
export { BotIcon } from "@chatballs/ui";

/** Круглый аватар агента: фон — акцент канала, внутри знак. */
export function BotAvatar({ size = 30, accent, color = "#fff" }: { size?: number; accent: string; color?: string }) {
  return (
    <span style={{ width: size, height: size, borderRadius: "50%", background: accent, display: "inline-flex", alignItems: "center", justifyContent: "center", flex: "none" }}>
      <BotIcon size={Math.round(size * 0.62)} color={color} />
    </span>
  );
}
