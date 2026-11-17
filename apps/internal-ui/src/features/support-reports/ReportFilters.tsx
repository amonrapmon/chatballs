import { DatePicker } from "antd";
import dayjs from "dayjs";
import { useState } from "react";
import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { FilterDropdown } from "../../shared/ui-controls";
import type { EmployeeGroupRef } from "../../types";
import { dateLabel, hasFilters, periodLabel } from "./presentation";
import { chooseReportingConnection, chooseReportingPlatform, connectionsForPlatform } from "./platformSelection";
import type { ReportDirectory, ReportFilters as Filters } from "./types";

export function ReportFilters({ filters, directory, groups, change, reset, periodOpen, setPeriodOpen }: {
  filters: Filters; directory: ReportDirectory; groups: EmployeeGroupRef[];
  change: (filters: Filters) => void; reset: () => void; periodOpen: boolean; setPeriodOpen: (open: boolean) => void;
}) {
  const [open, setOpen] = useState("");
  const connections = connectionsForPlatform(directory, filters.platform || "");
  const choices = [
    { key: "timezone" as const, options: directory.timezones.map((value) => ({ value, label: value })) },
    { key: "employee" as const, options: directory.employees.map((item) => ({ value: String(item.id), label: item.fullName || item.email })) },
    { key: "group" as const, options: groups.map((item) => ({ value: String(item.id), label: item.name })) },
    { key: "platform" as const, options: [
      ...(["web", "email", "telegram", "max", "vk"] as const).map((key) => ({ value: key.toUpperCase(), label: t(`reports.channel_${key}`) })),
      { value: "API_CONNECTOR", label: "API Connector" },
    ] },
    { key: "connection" as const, options: connections.map((item) => ({
      value: String(item.id),
      label: item.provider === "API_CONNECTOR" ? `${item.name} · ${item.displayProvider === "TELEGRAM" ? "Telegram" : item.displayProvider === "MAX" ? "MAX" : "API Connector"}` : item.name,
    })) },
  ];
  return <div className="report-filters">
    <label className="report-filter report-period"><span>{t("reports.period")}</span>
      <span className="report-range-field">
      <DatePicker.RangePicker value={[dayjs(filters.start), dayjs(filters.end)]} inputReadOnly allowClear={false} open={periodOpen} onOpenChange={setPeriodOpen}
        format={(value) => dateLabel(value.format("YYYY-MM-DD"), filters.timezone)}
        id={{ start: "report-start", end: "report-end" }} aria-label={t("reports.period")}
        suffixIcon={<Icon name="chevron" size={13} />} separator="–"
        onChange={(value) => value?.[0] && value[1] && change({ ...filters, start: value[0].format("YYYY-MM-DD"), end: value[1].format("YYYY-MM-DD") })} />
      <span className="report-range-label" aria-hidden="true">{periodLabel(filters)}</span>
      </span>
    </label>
    {choices.map(({ key, options }) => {
      const groupLabel = directory.restricted && key === "group" ? groups.map(row => row.name).join(", ") : t("reports.all");
      const all = key === "timezone" ? options : [{ value: "", label: t("reports.all") }, ...options];
      const value = filters[key] || "";
      return <div className={`report-filter report-filter-${key}`} key={key} title={key === "platform" ? "Мессенджер определяется текущими настройками подключения. При смене сервиса исторические события не переименовываются." : directory.restricted && key === "group" ? t("reports.controlled_groups_hint") : undefined}><span>{t(`reports.${key === "platform" ? "transport" : key}`)}</span>
        <FilterDropdown label={key === "group" && !value ? groupLabel : all.find((item) => item.value === value)?.label ?? t("reports.all")} options={all}
          selected={key === "group" && directory.restricted ? [value] : value && (key !== "timezone" || value !== directory.timezone) ? [value] : []} open={open === key} onOpenChange={(show) => setOpen(show ? key : "")}
          className="report-filter-trigger row-menu-button"
          onSelect={(selected) => {
            if (key === "platform") change(chooseReportingPlatform(filters, directory, selected));
            else if (key === "connection") change(chooseReportingConnection(filters, directory, selected));
            else change({ ...filters, [key]: selected });
            setOpen("");
          }} />
      </div>;
    })}
    <button className={`link report-reset ${hasFilters(filters) ? "" : "is-muted"}`} type="button" onClick={reset}>{t("reports.reset")}</button>
  </div>;
}
