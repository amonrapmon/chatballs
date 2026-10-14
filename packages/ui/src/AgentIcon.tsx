/** Контур агента из platform-expansion/chat-model.js; клиентский BotIcon
 * сохраняет отдельные заливку и моргание своего baseline. */
export function AgentIcon({ size = 17, strokeWidth = 1.8 }: { size?: number; strokeWidth?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M7 4.6h10a3.4 3.4 0 0 1 3.4 3.4v6.2a3.4 3.4 0 0 1-3.4 3.4h-6.2l-3.4 2.8v-2.8H7A3.4 3.4 0 0 1 3.6 14.2V8A3.4 3.4 0 0 1 7 4.6zM12 4.6V2.9M12 1.4v.01M9 9.4v1.4M15 9.4v1.4M9.2 13.4c.8 1 1.7 1.5 2.8 1.5s2-.5 2.8-1.5M1.6 9.8v2.6M22.4 9.8v2.6" />
    </svg>
  );
}
