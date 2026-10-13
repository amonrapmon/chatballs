import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { fetchParticipantLimit, saveParticipantLimit, type ParticipantLimit } from "../conversations/participantApi";
import { t } from "../../i18n";

export function useParticipantLimit() {
  const [saved, setSaved] = useState<ParticipantLimit | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetchParticipantLimit().then((value) => {
      if (!active) return;
      setSaved(value);
      setDraft(String(value.additionalParticipantLimit));
    }).catch((problem) => {
      if (active) setError(problem instanceof Error ? problem.message : t("common.request_failed"));
    });
    return () => { active = false; };
  }, []);

  async function save() {
    if (busy) return;
    setBusy(true);
    setFieldError("");
    setError("");
    try {
      // Validation belongs to the API: even an invalid draft gets its actual answer.
      const value = await saveParticipantLimit(draft.trim() === "" ? NaN : Number(draft));
      setSaved(value);
      setDraft(String(value.additionalParticipantLimit));
    } catch (problem) {
      // The shared API handler flattens validation errors to { detail }.
      if (problem instanceof ApiError && problem.status === 400) {
        setFieldError(problem.message);
      } else {
        setError(problem instanceof Error ? problem.message : t("common.request_failed"));
      }
    } finally {
      setBusy(false);
    }
  }

  return { saved, draft, setDraft, busy, fieldError, error, save };
}
