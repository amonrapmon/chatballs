import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AuthenticatedUser, OrganizationMembership, SessionUser } from "../types";

// Refresh the server's control area independently of ordinary membership.
export function useSupervision(user: SessionUser) {
  const [access, setAccess] = useState<OrganizationMembership>(user);
  useEffect(() => {
    if (user.role === "OWNER" || user.role === "ADMIN") { setAccess(user); return; }
    let active = true;
    async function refresh() {
      try {
        const payload = await api<{ user?: AuthenticatedUser }>("/api/v1/auth/session/");
        const membership = payload.user?.memberships.find((item) => item.organizationPublicId === user.organizationPublicId);
        if (active && membership) setAccess(membership);
      } catch { /* Resource operations keep enforcing current rights. */ }
    }
    void refresh();
    const timer = setInterval(refresh, 5000);
    window.addEventListener("focus", refresh);
    return () => { active = false; clearInterval(timer); window.removeEventListener("focus", refresh); };
  }, [user.organizationPublicId, user.role]);
  return access;
}
