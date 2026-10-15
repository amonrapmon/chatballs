import { useState } from "react";
import type { AgentRef } from "../agents/model";
import { SkillEditor } from "./SkillEditor";
import { SkillsLibrary } from "./SkillsLibrary";
import { SkillDeleteDialog } from "./SkillDeleteDialog";
import type { TemplateEditorBridge } from "./SkillTemplates";
import "./styles";
export function SkillsWorkspace({
  agents,
  back,
  openAgent,
  templateEditor,
}: {
  agents: AgentRef[];
  back: () => void;
  openAgent: (id: number) => void;
  templateEditor?: TemplateEditorBridge;
}) {
  const [selected, setSelected] = useState(() => new URLSearchParams(window.location.search).get("skill"));
  const [deleting, setDeleting] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);
  const open = (id: string | null) => {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("skill", id);
    else url.searchParams.delete("skill");
    window.history.replaceState(window.history.state, "", url);
    setSelected(id);
  };
  return (
    <>
      {selected ? (
        <SkillEditor
          key={selected}
          id={selected}
          back={() => open(null)}
          openAgent={openAgent}
          remove={setDeleting}
          templateEditor={templateEditor}
        />
      ) : (
        <SkillsLibrary
          key={generation}
          agents={agents}
          back={back}
          open={open}
          remove={setDeleting}
          openAgent={openAgent}
        />
      )}
      {deleting && (
        <SkillDeleteDialog
          id={deleting}
          close={() => setDeleting(null)}
          deleted={() => {
            setDeleting(null);
            open(null);
            setGeneration((value) => value + 1);
          }}
        />
      )}
    </>
  );
}
