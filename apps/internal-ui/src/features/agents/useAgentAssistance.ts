import { useRef, useState } from "react";

/** Pending intent is local; the authoritative value stays in the agent card. */
export function useAgentAssistance(enabled: boolean, busy: boolean, save: (value: boolean) => Promise<boolean>) {
  const [pending, setPending] = useState<boolean | null>(null);
  const [failedTarget, setFailedTarget] = useState<boolean | null>(null);
  const inFlight = useRef(false);

  async function change(value: boolean) {
    if (busy || inFlight.current) return;
    inFlight.current = true;
    setPending(value);
    setFailedTarget(null);
    try {
      if (!await save(value)) setFailedTarget(value);
    } catch {
      setFailedTarget(value);
    } finally {
      setPending(null);
      inFlight.current = false;
    }
  }

  return {
    checked: pending ?? enabled,
    saving: pending !== null,
    failed: failedTarget !== null,
    toggle: () => change(!enabled),
    retry: () => failedTarget !== null ? change(failedTarget) : Promise.resolve(),
  };
}
