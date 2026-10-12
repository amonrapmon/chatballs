import { useEffect, useRef, useState, type RefObject } from "react";

import { t } from "../../i18n";
import { useDebounced } from "../../shared/useDebounced";
import { renderReplyTemplate, searchTemplates, templateTaxonomy, templateVariables, type TemplateScope, type TemplateTaxon, type TemplateVariable } from "../reply-templates/api";
import type { TokenEditorHandle } from "../reply-templates/TokenEditor";
import type { ReplyTemplateRef } from "./model";

// Выбор шаблона из редактора (кадры T1–T3): кнопка «Шаблоны» и «/» в начале
// поля открывают один и тот же список с серверным поиском по названию и
// тексту. Выбранный шаблон подставляет сервер — для текущего диалога, по
// данным, которые видит сотрудник; клиент значений не передаёт.

export function useComposerTemplates({ text, setText, conversationId, editorRef }: {
  text: string;
  setText: (text: string) => void;
  conversationId: number | null;
  editorRef: RefObject<TokenEditorHandle | null>;
}) {
  const [visible, setVisible] = useState<ReplyTemplateRef[]>([]);
  const [open, setOpen] = useState(false);
  // Текст, при котором меню закрыли: то же «/…» его заново не открывает.
  const [dismissed, setDismissed] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<TemplateScope | "">("");
  const [variables, setVariables] = useState<TemplateVariable[]>([]);
  const [categories, setCategories] = useState<TemplateTaxon[]>([]);
  const [unfilledKeys, setUnfilledKeys] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [selected, setSelected] = useState(0);
  const [lastPage, setLastPage] = useState(1);
  const [pageCount, setPageCount] = useState(1);

  const slashQuery = text.startsWith("/") ? text.slice(1).trim() : null;
  const menuOpen = open || (slashQuery !== null && dismissed !== text);
  const search = useDebounced(slashQuery ?? query, 200);
  const listKey = `${conversationId}:${scope}:${search}`;
  const currentList = useRef(listKey);
  currentList.current = listKey;
  const currentConversation = useRef(conversationId);
  currentConversation.current = conversationId;

  useEffect(() => {
    let active = true;
    setOpen(false);
    setDismissed(null);
    setUnfilledKeys([]);
    setError("");
    Promise.all([templateVariables(), templateTaxonomy("categories")])
      .then(([catalog, cats]) => { if (active) { setVariables(catalog); setCategories(cats); } })
      .catch(() => { if (active) setError(t("settings.could_not_load_templates")); });
    return () => { active = false; };
  }, [conversationId]);

  // Отметка «закрыто» действует, пока текст тот же: изменённый, а затем
  // набранный заново запрос «/…» снова открывает меню.
  useEffect(() => {
    if (dismissed !== null && dismissed !== text) setDismissed(null);
  }, [text, dismissed]);

  useEffect(() => {
    if (!menuOpen) return undefined;
    let active = true;
    setLoading(true);
    setError("");
    searchTemplates({ q: search, scope: scope || undefined })
      .then((result) => {
        if (!active) return;
        setVisible(result.items);
        setSelected(0);
        setLastPage(result.page);
        setPageCount(result.pageCount);
      })
      .catch(() => { if (active) { setVisible([]); setError(t("settings.could_not_load_templates")); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [search, scope, menuOpen, conversationId]);

  function close() {
    setOpen(false);
    setDismissed(text);
    setQuery("");
  }

  async function loadMore() {
    if (loading || lastPage >= pageCount) return;
    const key = currentList.current;
    setLoading(true);
    try {
      const result = await searchTemplates({ q: search, scope: scope || undefined, page: lastPage + 1 });
      if (currentList.current !== key) return;
      setVisible((items) => [...items, ...result.items]);
      setLastPage(result.page);
    } catch {
      setError(t("settings.could_not_load_templates"));
    } finally {
      setLoading(false);
    }
  }

  async function apply(template: ReplyTemplateRef) {
    if (conversationId === null || applying) return;
    const target = conversationId;
    setApplying(true);
    setError("");
    try {
      const result = await renderReplyTemplate(template.id, target);
      // Пока шёл запрос, сотрудник открыл другой диалог: чужой текст не вставляем.
      if (target !== currentConversation.current) return;
      setText(result.text);
      setUnfilledKeys(result.unfilledKeys);
      setOpen(false);
      setDismissed(result.text);
      setQuery("");
      window.requestAnimationFrame(() => editorRef.current?.focus());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("settings.could_not_load_templates"));
    } finally {
      setApplying(false);
    }
  }

  return {
    visible, variables, categories, unfilledKeys, error, applying, loading, selected, scope, setScope, slashQuery, menuOpen,
    query: slashQuery ?? query,
    // При открытии через «/» запрос живёт в самом поле сообщения.
    setQuery: (value: string) => { if (slashQuery !== null) setText(`/${value}`); else setQuery(value); },
    toggle: () => {
      if (menuOpen) { close(); return; }
      setOpen(true);
      setDismissed(null);
    },
    close,
    apply,
    applySelected: () => { const item = visible[selected]; if (item) void apply(item); },
    loadMore,
    // Esc закрывает выбор и убирает набранное «/…».
    escape: () => { close(); if (slashQuery !== null) setText(""); },
    move: (delta: number) => setSelected((index) => (visible.length ? (index + delta + visible.length) % visible.length : 0)),
  };
}

export type ComposerTemplatesState = ReturnType<typeof useComposerTemplates>;
