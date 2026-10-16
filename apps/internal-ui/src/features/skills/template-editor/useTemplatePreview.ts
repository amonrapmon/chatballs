import { useEffect, useState } from "react";
import type { PreparedContent } from "@chatballs/ui";
import { skillError, type Configuration } from "../model";
import { diagnostics, exampleError, previewDraft, validateDraft, type Diagnostic } from "./api";

type Result = { key: string; errors: Diagnostic[]; content?: PreparedContent; failure: string; valid: boolean };
export function useTemplatePreview(configuration: Configuration, templateId: string, example: string) {
  const [generation, setGeneration] = useState(0);
  const key = JSON.stringify([configuration, templateId, example, generation]);
  const [result, setResult] = useState<Result | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    const timer = window.setTimeout(async () => {
      const next: Result = { key, errors: [], failure: "", valid: false };
      try {
        await validateDraft(configuration, controller.signal);
        next.valid = true;
      } catch (caught) {
        next.errors = diagnostics(caught);
        if (!next.errors.length) next.failure = skillError(caught);
      }
      if (!current) return;
      let data: unknown;
      try { data = JSON.parse(example); }
      catch { next.errors.push(exampleError()); }
      if (!next.errors.some((error) => error.origin === "example") && !next.failure) {
        try { next.content = await previewDraft(configuration, templateId, data, controller.signal); }
        catch (caught) {
          const errors = diagnostics(caught);
          // Preview includes configuration errors as well as data diagnostics.
          next.errors = [...next.errors.filter((error) => !errors.some((item) => JSON.stringify(item) === JSON.stringify(error))), ...errors];
          if (!errors.length) next.failure = skillError(caught);
        }
      }
      if (current) setResult(next);
    }, 300);
    return () => { current = false; clearTimeout(timer); controller.abort(); };
  }, [key]);
  return { ...(result?.key === key ? result : { errors: [], content: undefined, failure: "", valid: false }),
    pending: result?.key !== key, retry: () => setGeneration((value) => value + 1) };
}
