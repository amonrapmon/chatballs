import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { t } from "../../i18n";
import { fetchConversation } from "../conversations/conversationApi";
import type { ApiConversation } from "../conversations/model";
import { fetchQualityJobs, fetchQualitySettings, launchQuality } from "./api";
import { displayedJob, latestFirst } from "./presentation";
import type { QualityJob, QualitySettings } from "./types";

export function useQualityAnalysis(id: number, canLaunch: boolean) {
  const [jobs, setJobs] = useState<QualityJob[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [conversation, setConversation] = useState<ApiConversation | null>(null);
  const [settings, setSettings] = useState<QualitySettings | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [denied, setDenied] = useState(false);
  const operation = useRef<string | null>(null);
  const fail = useCallback((problem: unknown) => {
    if (problem instanceof ApiError && [403, 404].includes(problem.status)) {
      setDenied(true); setJobs([]); setConversation(null); setSettings(null);
    }
    setError(problem instanceof Error ? problem.message : t("common.request_failed"));
  }, []);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const result = await fetchQualityJobs(id);
        if (!active) return;
        setJobs(result.jobs); setDenied(false);
        const [detail, config] = await Promise.all([fetchConversation(id), canLaunch ? fetchQualitySettings() : Promise.resolve(null)]);
        if (active) { setConversation(detail); setSettings(config); }
      } catch (problem) { if (active) fail(problem); }
      finally { if (active) setLoaded(true); }
    }
    void load();
    return () => { active = false; };
  }, [id, canLaunch, fail]);
  useEffect(() => {
    if (!loaded || denied) return;
    let active = true;
    // Check access as well as pending jobs; a revoked scope must clear old results.
    const timer = window.setInterval(() => {
      fetchQualityJobs(id).then(result => { if (active) setJobs(result.jobs); }).catch(problem => { if (active) fail(problem); });
    }, jobs.some(job => ["WAITING", "RUNNING"].includes(job.state)) ? 1500 : 10000);
    return () => { active = false; window.clearInterval(timer); };
  }, [id, loaded, denied, jobs, fail]);
  async function launch() {
    if (busy || !canLaunch || denied) return;
    setBusy(true); setError("");
    operation.current ||= crypto.randomUUID();
    try {
      const job = await launchQuality(id, operation.current, jobs.length > 0);
      operation.current = null; setSelectedId(null);
      setJobs(previous => [job, ...previous.filter(row => row.id !== job.id)]);
    } catch (problem) { fail(problem); }
    finally { setBusy(false); }
  }
  function accept(job: QualityJob) { setJobs(previous => previous.map(row => row.id === job.id ? job : row)); }
  return { jobs: latestFirst(jobs), job: displayedJob(jobs, selectedId), select: setSelectedId, accept, fail,
    conversation, settings, loaded, busy, error, denied, launch };
}
