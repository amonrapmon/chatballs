import { useState } from "react";
import { usePagedResource } from "../../../shared/usePagedResource";
import { errorText, fetchReasons, saveReason, toggleReason } from "../../transfers/api";

export function useTransferReasons() {
  const list = usePagedResource(fetchReasons, null);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [errorId, setErrorId] = useState<number | null>(null);
  async function run(action: () => Promise<unknown>, id: number | null) {
    setBusy(true); setError(""); setErrorId(id);
    try {
      await action();
      if (id === null) setNewName("");
      setEditing(null);
      await list.reload();
    } catch (problem) { setError(errorText(problem)); }
    finally { setBusy(false); }
  }
  return {
    list, editing, draft, setDraft, newName, setNewName, busy, error, errorId,
    edit: (id: number, name: string) => { setEditing(id); setDraft(name); setError(""); },
    cancel: () => { setEditing(null); setError(""); },
    create: () => run(() => saveReason(newName), null),
    save: () => run(() => saveReason(draft, editing!), editing),
    toggle: (id: number, active: boolean) => run(() => toggleReason(id, active), id),
  };
}
