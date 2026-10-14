import { Dropdown } from "antd";
import { useState } from "react";
import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import type { EmployeeGroup } from "../../types";
import { ReportExportDialog } from "./ReportExportDialog";
import type { ReportDirectory, ReportFilters } from "./types";
import type { ExportFormat } from "./useReportExport";
import "./export.css";

export function ReportExport({ disabled, filters, directory, groups, generatedAt }: {
  disabled: boolean; filters: ReportFilters | null; directory: ReportDirectory | null;
  groups: EmployeeGroup[]; generatedAt?: string;
}) {
  const [open, setOpen] = useState(false);
  const [selection, setSelection] = useState<{ filters: ReportFilters; format: ExportFormat; generatedAt: string } | null>(null);
  const formats: ExportFormat[] = ["csv", "xlsx"];
  return <>
    <Dropdown disabled={disabled} open={open} onOpenChange={setOpen} trigger={["click"]} placement="bottomRight"
      overlayClassName="app-dropdown report-export-menu" menu={{ items: formats.map((format) => ({
        key: format, label: <button type="button"><Icon name="doc" size={15} /><span>{t(`reports.${format}`)}</span><small>{t(`reports.${format}_note`)}</small></button>,
      })), onClick: ({ key }) => {
        setOpen(false);
        if (filters && generatedAt) setSelection({ filters: { ...filters }, format: key as ExportFormat, generatedAt });
      } }}>
      <button className={`row-menu-button report-export-trigger ${open ? "is-open" : ""}`} type="button" disabled={disabled}>
        <Icon name="download" size={15} />{t("reports.export")}
      </button>
    </Dropdown>
    {selection && directory && <ReportExportDialog filters={selection.filters} initialFormat={selection.format}
      generatedAt={selection.generatedAt} directory={directory} groups={groups} onClose={() => setSelection(null)} />}
  </>;
}
