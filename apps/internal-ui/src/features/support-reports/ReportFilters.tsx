import { DatePicker } from "antd";
import dayjs from "dayjs";
import { useState } from "react";
import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { Button, FilterDropdown } from "../../shared/ui-controls";
import type { EmployeeGroupRef } from "../../types";
import { dateLabel, periodLabel } from "./presentation";
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
      { value: "API_CONNECTOR", label: t("reports.channel_connector") },
    ] },
    { key: "connection" as const, options: connections.map((item) => ({
      value: String(item.id),
      label: item.provider === "API_CONNECTOR" ? `${item.name} · ${item.displayProvider === "TELEGRAM" ? t("reports.channel_telegram") : item.displayProvider === "MAX" ? t("reports.channel_max") : item.displayProvider === "VK" ? t("reports.channel_vk") : t("reports.channel_connector")}` : item.name,
    })) },
  ];
  return <div className="report-filters">
    <div className="report-range-field">
      <DatePicker.RangePicker value={[dayjs(filters.start), dayjs(filters.end)]} inputReadOnly allowClear={false} open={periodOpen} onOpenChange={setPeriodOpen}
        format={(value) => dateLabel(value.format("YYYY-MM-DD"), filters.timezone)}
        id={{ start: "report-start", end: "report-end" }} aria-label={t("reports.period")}
        suffixIcon={<Icon name="chevron" size={13} />} separator="–"
        onChange={(value) => value?.[0] && value[1] && change({ ...filters, start: value[0].format("YYYY-MM-DD"), end: value[1].format("YYYY-MM-DD") })} />
      <span className="report-range-label" aria-hidden="true">
        <i className="ui-filter-caption">{t("reports.period")}:</i>
        <span className="ui-filter-label">{periodLabel(filters)}</span>
      </span>
    </div>
    {choices.map(({ key, options }) => {
      const restrictedGroup = key === "group" && directory.restricted;
      const groupLabel = restrictedGroup ? groups.map(row => row.name).join(", ") : t("reports.all");
      const all = key === "timezone" ? options : [{ value: "", label: t("reports.all") }, ...options];
      const value = filters[key] || "";
      const dropdown = <FilterDropdown key={key} caption={`${t(`reports.${key === "platform" ? "transport" : key}`)}:`}
        label={key === "group" && !value ? groupLabel : all.find((item) => item.value === value)?.label ?? t("reports.all")}
        options={all} selected={restrictedGroup || (value && (key !== "timezone" || value !== directory.timezone)) ? [value] : []}
        open={open === key} onOpenChange={(show) => setOpen(show ? key : "")}
        onSelect={(selected) => {
          if (key === "platform") change(chooseReportingPlatform(filters, directory, selected));
          else if (key === "connection") change(chooseReportingConnection(filters, directory, selected));
          else change({ ...filters, [key]: selected });
          setOpen("");
        }} />;
      const hint = key === "platform" ? t("reports.platform_current_hint") : restrictedGroup ? t("reports.controlled_groups_hint") : undefined;
      return hint ? <span className="report-filter-hint" key={key} title={hint}>{dropdown}</span> : dropdown;
    })}
    <Button variant="secondary" onClick={reset}>{t("reports.reset")}</Button>
  </div>;
}
