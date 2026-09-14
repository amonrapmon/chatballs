import { useEffect, useMemo, useRef, useState } from "react";

import { Icon } from "../../../shared/icons";
import { LoadingState } from "../../../shared/ui";
import { Button } from "../../../shared/ui-controls";
import type { RouteKey } from "../../../types";
import { downloadKnowledgeTemplate } from "./downloadKnowledgeTemplate";
import { parseKnowledgeYaml, type ParsedKnowledgeYaml } from "./parseKnowledgeYaml";
import {
  fetchKnowledgeCategories,
  fetchKnowledgeList,
  importKnowledge,
  type KnowledgeCategory,
  type KnowledgeImportReport,
  type KnowledgeItem,
} from "./model";
import { t, tn } from "../../../i18n";
import { readableSize } from "../../../shared/utils";
import { planRows } from "./knowledgeImportPlan";
import { KnowledgeImportPreview } from "./KnowledgeImportPreview";

export function KnowledgeImportPage({
  canManage,
  setRoute,
}: {
  canManage: boolean;
  setRoute: (route: RouteKey) => void;
}) {
  const [categories, setCategories] = useState<KnowledgeCategory[]>([]);
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<ParsedKnowledgeYaml | null>(null);
  const [report, setReport] = useState<KnowledgeImportReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    Promise.all([fetchKnowledgeCategories(), fetchKnowledgeList()])
      .then(([categoryPayload, itemPayload]) => {
        setCategories(categoryPayload.items);
        setItems(itemPayload.items);
      })
      .catch(() => setError(t("ai.could_not_load_categories_knowledge")))
      .finally(() => setLoading(false));
  }, []);

  const rows = useMemo(
    () => (parsed ? planRows(parsed, categories, items) : []),
    [categories, items, parsed],
  );
  const counts = {
    create: rows.filter((row) => row.action === "create").length,
    update: rows.filter((row) => row.action === "update").length,
    error: rows.filter((row) => row.action === "error").length,
  };
  const importable = rows.filter((row) => row.action !== "error");

  async function pick(selected: File) {
    setError("");
    setReport(null);
    setFile(selected);
    try {
      setParsed(parseKnowledgeYaml(await selected.text()));
    } catch (caught) {
      setParsed(null);
      setError(caught instanceof Error ? caught.message : t("ai.could_not_read_file"));
    }
  }

  async function submit() {
    if (importable.length === 0) return;
    setBusy(true);
    setError("");
    try {
      setReport(await importKnowledge(importable.map((row) => row.document)));
      setParsed(null);
      setFile(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("ai.could_not_import"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="knowledge-card">
      <div className="knowledge-card-head is-plain">
        <nav className="knowledge-breadcrumbs">
          <button className="link is-strong" type="button" onClick={() => setRoute("knowledge")}>{t("common.knowledge_base")}</button>
          <span><span className="knowledge-crumb-sep">/</span><b>{t("ai.yaml_import")}</b></span>
        </nav>
        <h2>{t("ai.material_import")}</h2>
        <p>{t("ai.file_parsed_before_anything_applied")}</p>
      </div>

      <div className="knowledge-plain-body">
        <div className="knowledge-import-layout">
          <input
            ref={fileInputRef}
            hidden
            accept=".yaml,.yml"
            type="file"
            onChange={(event) => {
              const selected = event.target.files?.[0];
              event.target.value = "";
              if (selected) void pick(selected);
            }}
          />

          <div className="knowledge-import-file">
            <i><Icon name="file" size={19} strokeWidth={1.8} /></i>
            <span>
              <strong>{file ? file.name : t("ai.no_file_selected")}</strong>
              <small>
                {file && parsed
                  ? t("ai.file_parsed_ok", { size: readableSize(file.size), count: tn("plural.documents", parsed.documents.length) })
                  : file
                    ? t("ai.file_not_parsed", { size: readableSize(file.size) })
                    : t("ai.yaml_shaped_as_documents_title")}
              </small>
            </span>
            <button type="button" onClick={() => fileInputRef.current?.click()}>
              {file ? t("ai.pick_another_file") : t("ai.pick_file")}
            </button>
            <button className="knowledge-import-template" type="button" onClick={downloadKnowledgeTemplate}>
              <Icon name="download" size={14} strokeWidth={1.9} />{t("ai.template")}</button>
          </div>

          {error && <div className="knowledge-form-error">{error}</div>}

          {loading && <LoadingState variant="inline" />}

          {report && (
            <div className="knowledge-import-report">
              <strong>{t("ai.import_finished")}</strong>
              <span>{t("ai.created")}<b>{report.created}</b>{t("ai.updated")}<b>{report.updated}</b>{t("ai.unchanged")}<b>{report.unchanged}</b>
              </span>
              {report.failed.length > 0 && (
                <ul>
                  {report.failed.map((failure, index) => (
                    <li key={index}>{failure.title ? `«${failure.title}»: ` : ""}{failure.detail}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {parsed && <KnowledgeImportPreview rows={rows} counts={counts} />}

          {parsed && (
            <div className="knowledge-import-actions">
              <span>{t("ai.import_category_policy")}</span>
              <Button variant="secondary" disabled={busy} onClick={() => setRoute("knowledge")}>{t("common.cancel")}</Button>
              <Button variant="primary" disabled={busy || !canManage || importable.length === 0} onClick={() => void submit()}>
                {t("ai.import_documents", { count: tn("plural.documents", importable.length) })}
              </Button>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
