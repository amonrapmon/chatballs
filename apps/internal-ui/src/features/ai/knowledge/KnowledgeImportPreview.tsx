import { t } from "../../../i18n";
import { ACTION_LABEL, type ImportAction, type ImportRow } from "./knowledgeImportPlan";

export function KnowledgeImportPreview({ rows, counts }: {
  rows: ImportRow[];
  counts: Record<ImportAction, number>;
}) {
  return (
    <div className="knowledge-import-plan">
      <div className="knowledge-import-plan-head">
        <strong>{t("ai.what_will_happen")}</strong>
        <span>
          {counts.create > 0 && <small className="is-create">{t("ai.count_create", { count: counts.create })}</small>}
          {counts.update > 0 && <small className="is-update">{t("ai.count_update", { count: counts.update })}</small>}
          {counts.error > 0 && <small className="is-error">{t("ai.count_error", { count: counts.error })}</small>}
        </span>
      </div>
      <table className="knowledge-import-table">
        <thead>
          <tr>
            <th>{t("ai.document")}</th>
            <th>CATEGORYPATH</th>
            <th>{t("ai.action")}</th>
            <th>{t("ai.note")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr className={row.action === "error" ? "is-error" : ""} key={`${row.document.title}-${index}`}>
              <td><code>{row.document.title}</code></td>
              <td className="knowledge-import-path">{row.path}</td>
              <td><span className={`knowledge-import-action is-${row.action}`}>{ACTION_LABEL[row.action]}</span></td>
              <td className="knowledge-import-note">{row.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
