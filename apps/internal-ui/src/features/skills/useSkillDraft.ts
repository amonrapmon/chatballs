import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { diagnostics, isParentError, validateDraft, type Diagnostic } from "./template-editor/api";
import { useTemplateSession } from "./template-editor/useTemplateSession";
import {
  configurationOf,
  emptyConfiguration,
  getOrdersBasis,
  getSkill,
  isConflict,
  requestFor,
  saveSkill,
  skillError,
  validateConfiguration,
  type Configuration,
  type SaveRequest,
  type SkillDetail,
} from "./model";

export function useSkillDraft(id: string) {
  const [saved, setSaved] = useState<SkillDetail | null>(null);
  const [draft, setDraft] = useState<Configuration>(emptyConfiguration);
  const [loading, setLoading] = useState(id !== "new");
  const [failure, setFailure] = useState<"missing" | "forbidden" | "load" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [basis, setBasis] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [validationErrors, setValidationErrors] = useState<Diagnostic[]>([]);
  const validation = useRef<Diagnostic[]>([]);
  const examples = useTemplateSession();
  const pending = useRef<SaveRequest | null>(null);
  const lastBasis = useRef<string | null>(null);
  const savedId = useRef(id === "new" ? null : id);
  const loadGeneration = useRef(0);
  const baseline = saved ? configurationOf(saved) : emptyConfiguration();
  const dirty = examples.dirty || JSON.stringify(draft) !== JSON.stringify(baseline);
  const load = useCallback(async () => {
    if (!savedId.current) return;
    const generation = ++loadGeneration.current;
    setLoading(true);
    setFailure(null);
    try {
      const { skill } = await getSkill(savedId.current);
      if (generation !== loadGeneration.current) return;
      setSaved(skill);
      setDraft(configurationOf(skill));
      setError("");
      setConflict(false);
      setValidationErrors([]);
      validation.current = [];
      examples.reset();
      pending.current = null;
    } catch (caught) {
      if (generation !== loadGeneration.current) return;
      setFailure(
        caught instanceof ApiError && caught.status === 403
          ? "forbidden"
          : caught instanceof ApiError && caught.status === 404
            ? "missing"
            : "load",
      );
    } finally {
      if (generation === loadGeneration.current) setLoading(false);
    }
  }, [id]);
  useEffect(() => {
    void load();
    return () => {
      loadGeneration.current += 1;
    };
  }, [load]);

  async function save() {
    if (busy || conflict) return false;
    setAttempted(true);
    validation.current = [];
    setValidationErrors([]);
    if (Object.keys(validateConfiguration(draft)).length) return false;
    setBusy(true);
    setError("");
    lastBasis.current = null;
    const body = requestFor(draft, saved?.revision, pending.current);
    pending.current = body;
    try {
      await validateDraft(draft);
      const { skill } = await saveSkill(saved?.id ?? null, body);
      savedId.current = skill.id;
      if (id === "new") {
        const address = new URL(window.location.href);
        address.searchParams.set("skill", skill.id);
        window.history.replaceState(window.history.state, "", address);
      }
      setSaved(skill);
      setDraft(configurationOf(skill));
      pending.current = null;
      setValidationErrors([]);
      examples.markSaved();
      return true;
    } catch (caught) {
      validation.current = diagnostics(caught);
      setValidationErrors(validation.current);
      setError(skillError(caught));
      setConflict(isConflict(caught));
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function changeBasis(next: string) {
    setBusy(true);
    setError("");
    lastBasis.current = next;
    try {
      const config = next === "orders" ? (await getOrdersBasis()).configuration : emptyConfiguration();
      setDraft(config);
      setBasis(next);
      setAttempted(false);
      setValidationErrors([]);
      validation.current = [];
      examples.reset();
    } catch (caught) {
      setError(skillError(caught));
    } finally {
      setBusy(false);
    }
  }
  const retry = () => (lastBasis.current !== null ? changeBasis(lastBasis.current) : save());
  const reset = () => {
    setDraft(baseline);
    setBasis("");
    if (!conflict) setError("");
    setAttempted(false);
    setValidationErrors([]);
    validation.current = [];
    examples.reset();
  };
  return {
    saved,
    draft,
    setDraft: (next: Configuration) => {
      setDraft(next);
      validation.current = [];
      setValidationErrors([]);
      if (!conflict) setError("");
    },
    dirty,
    loading,
    failure,
    busy,
    error,
    conflict,
    basis,
    attempted,
    save,
    retry,
    load,
    changeBasis,
    reset,
    validationErrors,
    exampleInputs: examples.inputs,
    setExampleInputs: examples.change,
    exampleSelections: examples.selections,
    selectExample: examples.select,
    templateTouches: examples.touched,
    touchTemplate: examples.touch,
    parentInvalid: () => Object.keys(validateConfiguration(draft)).length > 0 || validation.current.some(isParentError),
  };
}
