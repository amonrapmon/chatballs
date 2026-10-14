import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { useRealtimeEvent } from "../realtime/RealtimeProvider";
import { fetchDayReports, fetchReport, fetchReportDirectory, fetchWaitingReplies } from "./api";
import { initialFilters, reportPeriod } from "./period";
import type { DayReport, ReportDirectory, ReportFilters, SupportReport } from "./types";

type Result = { report: SupportReport; days: DayReport[]; waiting: Record<number, number> };
export function useSupportReport() {
  const [directory, setDirectory] = useState<ReportDirectory | null>(null);
  const [filters, setFilters] = useState<ReportFilters | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string>();
  const [denied, setDenied] = useState(false);
  const [revision, setRevision] = useState(0);
  const retry = () => setRevision((value) => value + 1);

  useRealtimeEvent("work_status.changed", retry);
  useRealtimeEvent("inbox.changed", retry);

  useEffect(() => {
    if (directory) return;
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    setErrorMessage(undefined);
    void fetchReportDirectory(controller.signal).then((data) => {
      if (controller.signal.aborted) return;
      setDirectory(data);
      setFilters(initialFilters(data.timezone));
    }).catch((reason) => {
      if (controller.signal.aborted) return;
      setDenied(reason instanceof ApiError && [401, 403].includes(reason.status));
      setErrorMessage(reason instanceof ApiError ? reason.message : undefined);
      setError(true);
      setLoading(false);
    });
    return () => controller.abort();
  }, [directory, revision]);

  useEffect(() => {
    if (!filters) return;
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    setErrorMessage(undefined);
    setResult(null);
    void (async () => {
      const period = reportPeriod(filters);
      const [report, days, waiting, currentDirectory] = await Promise.all([
        fetchReport(period, controller.signal), fetchDayReports(filters, controller.signal), fetchWaitingReplies(period, controller.signal), fetchReportDirectory(controller.signal),
      ]);
      if (!controller.signal.aborted) { setDirectory(currentDirectory); setResult({ report, days, waiting }); setDenied(false); }
    })().catch((reason) => {
      if (controller.signal.aborted) return;
      setDenied(reason instanceof ApiError && [401, 403].includes(reason.status));
      setErrorMessage(reason instanceof ApiError ? reason.message : undefined);
      setError(true);
      setResult(null);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [filters, revision]);

  // Current load is a request-time snapshot, also when the period is historical.
  useEffect(() => {
    const timer = window.setInterval(retry, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  return { directory, filters, setFilters, result, loading, error, errorMessage, denied, retry,
    reset: () => directory && setFilters(initialFilters(directory.timezone)) };
}
