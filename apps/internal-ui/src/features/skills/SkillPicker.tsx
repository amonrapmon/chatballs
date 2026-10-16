import { Modal } from "antd";
import { useState } from "react";
import { t, tn } from "../../i18n";
import { SearchInput, Button } from "../../shared/ui-controls";
import { EmptyState, ErrorScreen, LoadingState, PermissionScreen } from "../../shared/ui";
import { Pagination } from "../../shared/Pagination";
import { useSkillPicker } from "./useSkillPicker";
export function SkillPicker({
  agentId,
  name,
  close,
  changed,
}: {
  agentId: number;
  name: string;
  close: () => void;
  changed: () => void;
}) {
  const { query, setQuery, list, selected, setSelected, busy, error, conflict, attached, connect, reloadSelected } =
    useSkillPicker(agentId, close, changed);
  const [refresh, setRefresh] = useState(false);
  return (
    <Modal
      open
      width={560}
      title={t("skills.connect_title", { name })}
      onCancel={() => {
        if (!busy) close();
      }}
      footer={
        <div className="skill-actions">
          <Button variant="secondary" disabled={busy} onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button
            variant="primary"
            disabled={busy || conflict || !Object.keys(selected).length || list.forbidden}
            onClick={() => void connect()}>
            {tn("skills.connect_count", Object.keys(selected).length)}
          </Button>
        </div>
      }>
      <p>{t("skills.connect_lead")}</p>
      <SearchInput
        clearable
        value={query}
        onChange={(value) => setQuery(value.slice(0, 200))}
        placeholder={t("skills.search")}
      />
      {list.forbidden ? (
        <PermissionScreen onReturn={close} />
      ) : list.errorText ? (
        <ErrorScreen retry={() => void list.reload()} />
      ) : list.loading ? (
        <LoadingState />
      ) : !list.total ? (
        <EmptyState title={t("skills.no_results")} />
      ) : (
        <div className="skill-picker">
          {list.items.map((skill) => (
            <label
              key={skill.id}
              className={`skill-pick ${selected[skill.id] ? "is-selected" : ""} ${attached(skill) ? "is-attached" : ""}`}>
              <input
                type="checkbox"
                checked={attached(skill) || !!selected[skill.id]}
                disabled={busy || attached(skill)}
                onChange={() =>
                  setSelected((current) => {
                    const next = { ...current };
                    if (next[skill.id]) delete next[skill.id];
                    else next[skill.id] = skill;
                    return next;
                  })
                }
              />
              <span>
                <strong>{skill.name}</strong>
                <small>{skill.description}</small>
                <small>
                  {skill.templateCount
                    ? tn("skills.template_count", skill.templateCount)
                    : t("skills.instruction_only")}{" "}
                  · {tn("skills.used", skill.agentCount)}
                </small>
              </span>
              {attached(skill) && <span className="skill-chip">{t("skills.already")}</span>}
            </label>
          ))}
          {list.pageCount > 1 && <Pagination page={list.page} pageCount={list.pageCount} onPage={list.setPage} />}
        </div>
      )}
      <p className="skill-notice">{t("skills.bounds_rights")}</p>
      {error && (
        <div className="skill-notice is-error" role="alert">
          {error}
          {conflict && (
            <Button variant="secondary" disabled={busy} onClick={() => setRefresh(true)}>
              {t("skills.refresh")}
            </Button>
          )}
        </div>
      )}
      <Modal
        open={refresh}
        title={t("skills.replace")}
        okText={t("skills.replace_action")}
        cancelText={t("common.cancel")}
        onCancel={() => setRefresh(false)}
        onOk={() => {
          setRefresh(false);
          void reloadSelected();
        }}
      />
    </Modal>
  );
}
