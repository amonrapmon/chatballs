type Guard = (proceed: () => void) => void;
let current: Guard | null = null;
let guardedUrl = "";
export function registerNavigationGuard(guard: Guard) {
  current = guard;
  guardedUrl = window.location.href;
  return () => {
    if (current === guard) current = null;
  };
}
// popstate has already changed the URL. Keep the editor address until the user
// accepts leaving, and only then apply the destination to both URL and content.
export function requestHistoryNavigation(proceed: () => void) {
  if (!current) {
    proceed();
    return;
  }
  const target = window.location.href;
  const targetState = window.history.state;
  window.history.replaceState(null, "", guardedUrl);
  current(() => {
    window.history.replaceState(targetState, "", target);
    proceed();
  });
}
export function requestNavigation(proceed: () => void) {
  if (current)
    current(() => {
      current = null;
      proceed();
    });
  else proceed();
}
export function releaseNavigationGuard() {
  current = null;
}
