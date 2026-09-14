import { Modal } from "antd";
import { useEffect, useMemo, useState } from "react";

import { LoadingState } from "../../shared/ui";
import { Button, SearchInput } from "../../shared/ui-controls";
import { AgentKnowledgeGroup } from "./AgentKnowledgeGroup";
import { filterGroups, loadChoiceGroups, pickedIds, pickedInGroup, type ChoiceGroup } from "./agentKnowledgeGroups";
import type { AgentCard } from "./model";
import { t } from "../../i18n";

// «Выбрать» в блоке «Знания» карточки агента (кадры G3/G5): материалы
// библиотеки и опубликованные статьи порталов, разложенные по категориям и
// порталам. Агент отвечает только по явно выбранным знаниям
// (ADR-CHATBALLS-0041 §8).
//
// Развёрнуты сразу только те группы, где уже что-то выбрано: так видно, что
// агент читает сейчас, а остальное дерево не занимает окно целиком.

export function AgentKnowledgeDialog({ card, onClose, onSave }: {
  card: AgentCard;
  onClose: () => void;
  onSave: (selection: { knowledgeIds: number[]; articleIds: number[] }) => Promise<void>;
}) {
  const [groups, setGroups] = useState<ChoiceGroup[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [search, setSearch] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [closed, setClosed] = useState<Set<string>>(() => new Set());
  const [picked, setPicked] = useState<Set<string>>(
    () => new Set([
      ...card.knowledge.map((item) => `k${item.id}`),
      ...card.portalArticles.map((article) => `a${article.id}`),
    ]),
  );

  useEffect(() => {
    let cancelled = false;
    loadChoiceGroups()
      .then((loaded) => {
        if (cancelled) return;
        setGroups(loaded);
        setClosed(new Set(loaded.filter((group) => pickedInGroup(group, picked) === 0).map((group) => group.key)));
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => { cancelled = true; };
    // Набор выбранного на момент загрузки берётся из карточки и до ответа
    // сервера не меняется — перезапускать загрузку на каждый клик незачем.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const visible = useMemo(() => filterGroups(groups ?? [], search), [groups, search]);
  const searching = Boolean(search.trim());

  function toggle(keys: string[], pick: boolean) {
    setPicked((current) => {
      const next = new Set(current);
      keys.forEach((key) => (pick ? next.add(key) : next.delete(key)));
      return next;
    });
  }

  async function submit() {
    if (groups === null) return;
    setSaving(true);
    setError("");
    try {
      await onSave(pickedIds(groups, picked));
      onClose();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("ai.could_not_save_selection"));
      setSaving(false);
    }
  }

  return (
    <Modal className="agent-knowledge-modal" open width={620} title={t("ai.select_knowledge")} onCancel={onClose} footer={null} destroyOnClose>
      <p className="agent-create-lead">{t("ai.agent_answers_only_from_selected")}</p>
      <SearchInput className="agent-knowledge-search" placeholder={t("ai.search_by_title")} value={search} onChange={setSearch} />
      {groups === null && !failed && <LoadingState />}
      {failed && <div className="agent-form-error">{t("ai.could_not_load_material_list")}</div>}
      {groups !== null && (
        <>
          <div className="agent-knowledge-summary">{t("common.selected_count", { count: picked.size })}</div>
          <div className="agent-knowledge-choices">
            {visible.length === 0 && <p className="agent-knowledge-nothing">{t("common.nothing_found")}</p>}
            {visible.map((group) => (
              <AgentKnowledgeGroup
                group={group}
                key={group.key}
                open={searching || !closed.has(group.key)}
                picked={picked}
                onToggleAll={toggle}
                onToggleChoice={(key) => toggle([key], !picked.has(key))}
                onToggleOpen={() => setClosed((current) => {
                  const next = new Set(current);
                  if (next.has(group.key)) next.delete(group.key);
                  else next.add(group.key);
                  return next;
                })}
              />
            ))}
          </div>
        </>
      )}
      {error && <div className="agent-form-error">{error}</div>}
      <div className="agent-create-actions">
        <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
        <Button variant="primary" disabled={groups === null || saving} onClick={() => void submit()}>
          {saving ? t("ai.saving") : t("common.save")}
        </Button>
      </div>
    </Modal>
  );
}
