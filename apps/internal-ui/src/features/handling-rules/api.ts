import { api } from "../../api/client";
import type { HandlingRule, RuleKind, RuleValues } from "./types";

const BASE = "/api/v1/conversations/";
export const fetchRules = (signal: AbortSignal) => api<{ items: HandlingRule[] }>(`${BASE}rules/`, { signal });
export const patchRule = (kind: RuleKind, changes: Partial<RuleValues>) =>
  api<{ rule: HandlingRule }>(`${BASE}rules/${kind}/`, { method: "PATCH", body: JSON.stringify(changes) });
