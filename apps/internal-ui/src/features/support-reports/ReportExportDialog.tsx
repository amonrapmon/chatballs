import { Modal } from "antd";
import { t } from "../../i18n";
import { Button } from "../../shared/ui-controls";
import type { EmployeeGroupRef } from "../../types";
import { ReportExportParameters } from "./ReportExportParameters";
import type { ReportDirectory, ReportFilters } from "./types";
import { useReportExport, type ExportFormat } from "./useReportExport";

export function ReportExportDialog({ filters, directory, groups, generatedAt, initialFormat, onClose }: {
  filters: ReportFilters; directory: ReportDirectory; groups: EmployeeGroupRef[];
  generatedAt: string; initialFormat: ExportFormat; onClose: () => void;
}) {
  const state = useReportExport(filters, initialFormat, onClose, directory);
  return <Modal open centered width={520} className="report-export-dialog" title={null} footer={null} closable={false}
    onCancel={state.cancel} destroyOnHidden aria-labelledby="report-export-title">
    <header><h3 id="report-export-title">{t("reports.export_title")}</h3><p>{t("reports.export_lead")}</p></header>
    <div className="report-export-formats">{(["csv", "xlsx"] as const).map((format) =>
      <button type="button" key={format} className={format === state.format ? "is-selected" : ""} disabled={state.busy}
        aria-pressed={format === state.format} onClick={() => state.setFormat(format)}>{t(`reports.${format}`)}</button>)}</div>
    <ReportExportParameters filters={filters} directory={directory} groups={groups} generatedAt={generatedAt} />
    {state.busy && <div className="report-export-progress" role="status">{t("reports.preparing")}</div>}
    {state.error && <div className="report-export-error" role="alert">{t("reports.export_error")}</div>}
    <footer><small>{state.error ? "" : t("reports.download_note")}</small>
      <Button variant="secondary" onClick={state.cancel}>{t("common.cancel")}</Button>
      <Button variant="primary" disabled={state.busy} onClick={() => void state.prepare()}>
        {t(state.busy ? "reports.preparing_button" : state.error ? "reports.retry" : "reports.export")}
      </Button>
    </footer>
  </Modal>;
}
