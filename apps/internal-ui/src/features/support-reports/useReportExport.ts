import { useEffect, useRef, useState } from "react";
import { downloadReport } from "./api";
import { reportPeriod } from "./period";
import type { ReportFilters } from "./types";

export type ExportFormat = "csv" | "xlsx";

/** Each dialog owns its filter snapshot and aborts work when it closes. */
export function useReportExport(filters: ReportFilters, initialFormat: ExportFormat, onClose: () => void) {
  const [format, setFormat] = useState(initialFormat);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState(false);
  const request = useRef<AbortController | null>(null);
  const cancel = () => { request.current?.abort(); onClose(); };
  const prepare = async () => {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError(false);
    try {
      const blob = await downloadReport(reportPeriod(filters), format, controller.signal);
      controller.signal.throwIfAborted();
      const url = URL.createObjectURL(blob);
      try {
        const link = document.createElement("a");
        link.href = url;
        link.download = `support-report-${filters.start}-${filters.end}.${format}`;
        link.click();
      } finally {
        window.setTimeout(() => URL.revokeObjectURL(url), 0);
      }
      onClose();
    } catch {
      if (!controller.signal.aborted) setError(true);
    } finally {
      request.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  };
  useEffect(() => {
    const timer = window.setTimeout(() => void prepare(), 0);
    return () => { window.clearTimeout(timer); request.current?.abort(); };
  }, []);
  return { format, setFormat, busy, error, prepare, cancel };
}
