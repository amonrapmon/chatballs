import { useEffect, useRef, useState } from "react";
import { registerNavigationGuard, releaseNavigationGuard } from "../../shared/navigationGuard";
export function useSkillLeaveGuard(dirty: boolean) {
  const [pending, setPending] = useState<(() => void) | null>(null);
  const cleanup = useRef<() => void>(() => undefined);
  const [generation, setGeneration] = useState(0);
  useEffect(() => {
    if (!dirty) return;
    const unregister = registerNavigationGuard((proceed) => setPending(() => proceed));
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    // Native entity links and organization switches use document navigation.
    const click = (event: MouseEvent) => {
      const link = (event.target as HTMLElement).closest<HTMLAnchorElement>("a[href]");
      if (!link || link.target === "_blank" || event.ctrlKey || event.metaKey || event.button !== 0) return;
      event.preventDefault();
      setPending(() => () => {
        window.removeEventListener("beforeunload", warn);
        window.location.assign(link.href);
      });
    };
    document.addEventListener("click", click);
    cleanup.current = () => {
      unregister();
      window.removeEventListener("beforeunload", warn);
      document.removeEventListener("click", click);
    };
    return () => cleanup.current();
  }, [dirty, generation]);
  const proceed = () => {
    cleanup.current();
    releaseNavigationGuard();
    const action = pending;
    setPending(null);
    action?.();
    setGeneration((value) => value + 1);
  };
  return {
    pending,
    proceed,
    stay: () => setPending(null),
    request: (action: () => void) => (dirty ? setPending(() => action) : action()),
  };
}
