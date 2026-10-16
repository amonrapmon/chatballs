import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { useRealtimeEvent } from "../realtime/RealtimeProvider";
import { allowedFilters, reportScopeKey } from "./access";
import { fetchDayReports, fetchReport, fetchReportDirectory } from "./api";
import { initialFilters, reportPeriod } from "./period";
import type { DayReport, ReportDirectory, ReportFilters, SupportReport } from "./types";

type Result = { report: SupportReport; days: DayReport[]; waiting: Record<number, number>; scopeKey: string; filters: ReportFilters };
export function useSupportReport() {
  const [directory, setDirectory] = useState<ReportDirectory | null>(null);
  const [filters, setFilters] = useState<ReportFilters | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string>();
  const [revision, setRevision] = useState(0);
  const retry = () => setRevision(value => value + 1);
  const scopeKey = reportScopeKey(directory);
  const available = directory?.actions.includes("reports.view") ?? false;
  useRealtimeEvent("work_status.changed", retry);
  useRealtimeEvent("inbox.changed", retry);

  // Refresh current grants independently of the heavy period calculations.
  useEffect(() => {
    const controller = new AbortController();
    let pending = false;
    async function refresh() {
      if (pending) return;
      pending = true;
      try {
        const data = await fetchReportDirectory(controller.signal);
        if (controller.signal.aborted) return;
        setDirectory(data);
        setFilters(previous => previous ? allowedFilters(previous, data) : initialFilters(data.timezone));
        if (!data.actions.includes("reports.view")) { setResult(null); setLoading(false); }
      } catch (reason) {
        if (controller.signal.aborted) return;
        setDirectory(null); setResult(null); setLoading(false); setError(true);
        setErrorMessage(reason instanceof ApiError ? reason.message : undefined);
      } finally { pending = false; }
    }
    void refresh();
    const timer = window.setInterval(refresh, 5000);
    window.addEventListener("focus", refresh);
    return () => { controller.abort(); window.clearInterval(timer); window.removeEventListener("focus", refresh); };
  }, [revision]);

  useEffect(() => {
    if (!filters || !available) return;
    const controller = new AbortController();
    setLoading(true); setError(false); setErrorMessage(undefined); setResult(null);
    void (async () => {
      const [report, days] = await Promise.all([
        fetchReport(reportPeriod(filters), controller.signal), fetchDayReports(filters, controller.signal),
      ]);
      if (!controller.signal.aborted) setResult({ report, days, filters, scopeKey,
        waiting: Object.fromEntries(report.employees.map(row => [row.employee, row.waitingReplies])) });
    })().catch(reason => {
      if (controller.signal.aborted) return;
      setErrorMessage(reason instanceof ApiError ? reason.message : undefined);
      setError(true); setResult(null);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [filters, scopeKey, available, revision]);

  useEffect(() => {
    const timer = window.setInterval(retry, 60_000);
    return () => window.clearInterval(timer);
  }, []);
  const current = available && result?.scopeKey === scopeKey && result.filters === filters ? result : null;
  return { directory, scopeKey, available, filters, setFilters, result: current, loading, error, errorMessage, retry,
    reset: () => directory && setFilters(initialFilters(directory.timezone)) };
}
