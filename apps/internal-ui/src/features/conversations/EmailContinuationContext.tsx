import { createContext, useContext, type ReactNode } from "react";
import { useConversationEmail } from "./useConversationEmail";
import "./email-continuation.css";

const Context = createContext<ReturnType<typeof useConversationEmail> | null>(null);
export function EmailContinuationProvider({ id, enabled, messageIds, children }: { id: number; enabled: boolean; messageIds: number[]; children: ReactNode }) {
  const value = useConversationEmail(id, enabled, messageIds.join(","));
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export const useEmailContinuation = () => useContext(Context);
