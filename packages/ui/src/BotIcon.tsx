import { useId } from "react";

/** Утверждённый знак агента: общая геометрия для виджета и предпросмотра. */
export function BotIcon({ size = 24, color = "currentColor", blink = true }: {
  size?: number; color?: string; blink?: boolean;
}) {
  const maskId = useId();
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill={color} aria-hidden="true" style={{ display: "block" }}>
      <mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width="48" height="48">
        <rect width="48" height="48" fill="white" />
        <g style={blink ? { transformOrigin: "24px 20px", animation: "wcBotBlink 4.2s infinite" } : undefined}>
          <rect x="15" y="16.4" width="4" height="7.2" rx="2" fill="black" />
          <rect x="29" y="16.4" width="4" height="7.2" rx="2" fill="black" />
        </g>
        <path d="M17.6 26.4c1.7 2.4 3.9 3.6 6.4 3.6s4.7-1.2 6.4-3.6" fill="none" stroke="black" strokeWidth="2.6" strokeLinecap="round" />
      </mask>
      <circle cx="24" cy="3.6" r="2.4" />
      <rect x="22.8" y="4.8" width="2.4" height="5" />
      <rect x="2.2" y="18" width="2.6" height="8.4" rx="1.3" />
      <rect x="43.2" y="18" width="2.6" height="8.4" rx="1.3" />
      <path mask={`url(#${maskId})`} d="M14 9.2h20a6.8 6.8 0 0 1 6.8 6.8v12.4a6.8 6.8 0 0 1-6.8 6.8H21.6l-6.4 5.2a.9.9 0 0 1-1.5-.7v-4.5h-.3A6.8 6.8 0 0 1 7.2 28.4V16A6.8 6.8 0 0 1 14 9.2Z" />
    </svg>
  );
}
