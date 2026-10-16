import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { fetchQualityEvidence } from "./api";
import type { QualityConclusion, QualityEvidence } from "./types";
import { QualityEvidenceList } from "./QualityEvidenceList";

export function QualityEvidenceLinks({ evidence, organizationId, fail }: {
  evidence: QualityConclusion["evidence"]; organizationId: string; fail: (problem: unknown) => void;
}) {
  const [messages, setMessages] = useState<QualityEvidence[]>([]);
  useEffect(() => {
    let active = true;
    void Promise.all(evidence.map(ref => fetchQualityEvidence(ref.url).catch(problem => {
      if (active && problem instanceof ApiError && problem.status === 403) fail(problem);
      return null;
    }))).then(rows => { if (active) setMessages(rows.filter((row): row is QualityEvidence => Boolean(row))); });
    return () => { active = false; };
  }, [evidence, fail]);
  return <QualityEvidenceList messages={messages} organizationId={organizationId} />;
}
