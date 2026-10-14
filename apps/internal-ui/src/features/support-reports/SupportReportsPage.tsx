import { useState } from "react";
import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { UnderlineTabs } from "../../shared/ui-controls";
import type { EmployeeGroup } from "../../types";
import { ReportChart } from "./ReportChart";
import { ReportEmployees } from "./ReportEmployees";
import { ReportExport } from "./ReportExport";
import { ReportFilters } from "./ReportFilters";
import { ReportMetrics } from "./ReportMetrics";
import { ReportState } from "./ReportState";
import { ReportWorkload } from "./ReportWorkload";
import { coverageTitle, emptyPeriod } from "./presentation";
import type { ReportTab } from "./types";
import { useSupportReport } from "./useSupportReport";
import "./styles.css";

export function SupportReportsPage({ groups }: { groups: EmployeeGroup[] }) {
  const state = useSupportReport();
  const [tab, setTab] = useState<ReportTab>("conversations");
  const [periodOpen, setPeriodOpen] = useState(false);
  const { result, filters, directory } = state;
  const empty = result && tab === "conversations" && emptyPeriod(result.report);
  return <div className="support-reports">
    <div className="report-header"><div><h2>{t("reports.title")}</h2><p>{t("reports.lead")}</p></div>
      <ReportExport disabled={state.loading || state.error || !result || Boolean(empty)} filters={filters} directory={directory} groups={groups} generatedAt={result?.report.generatedAt} />
    </div>
    {filters && directory && <ReportFilters filters={filters} directory={directory} groups={groups} change={state.setFilters} reset={state.reset} periodOpen={periodOpen} setPeriodOpen={setPeriodOpen} />}
    <UnderlineTabs value={tab} onChange={setTab} items={[{ key: "conversations", label: t("reports.conversations") }, { key: "workload", label: t("reports.workload") }]} />
    {state.loading ? <ReportMetrics report={null} /> : state.error || empty ?
      <ReportState error={state.error} errorMessage={state.errorMessage} filters={filters}
        group={groups.find((item) => String(item.id) === filters?.group)?.name}
        connection={directory?.connections.find((item) => String(item.id) === filters?.connection)?.name}
        retry={state.retry} reset={state.reset} selectPeriod={() => setPeriodOpen(true)} /> : result && directory && <>
        {!result.report.coverage.complete && <div className="report-coverage" title={coverageTitle(result.report)}><Icon name="warning" size={16} />
          <span><b>{t("reports.partial_banner")}</b> {result.report.coverage.availableFrom ? coverageTitle(result.report) : t("reports.partial_note")}</span>
        </div>}
        {tab === "conversations" ? <><ReportMetrics report={result.report} /><ReportChart days={result.days} /><ReportEmployees report={result.report} employees={directory.employees} /></>
          : <ReportWorkload report={result.report} employees={directory.employees} waiting={result.waiting} />}
      </>}
  </div>;
}
