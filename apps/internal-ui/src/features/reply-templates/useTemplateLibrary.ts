import { useEffect, useState } from "react";

import { t } from "../../i18n";
import { useDebounced } from "../../shared/useDebounced";
import { searchTemplates, templatePermissions, templateTaxonomy, type TemplatePage, type TemplateScope, type TemplateTaxon } from "./api";

// Состояние библиотеки: область, поиск, фильтры и страница — всё считает
// сервер. Права и справочники читаются один раз и после каждого изменения.

export function useTemplateLibrary() {
  const [scope, setScope] = useState<TemplateScope>("SHARED");
  const [q, setQ] = useState("");
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [tagIds, setTagIds] = useState<number[]>([]);
  const [page, setPage] = useState(1);
  const [version, setVersion] = useState(0);
  // null — права ещё не пришли: до ответа нельзя показывать ни «только
  // использование», ни управление общими.
  const [canManageShared, setCanManageShared] = useState<boolean | null>(null);
  const [counts, setCounts] = useState<Record<TemplateScope, number> | undefined>();
  const [categories, setCategories] = useState<TemplateTaxon[]>([]);
  const [tags, setTags] = useState<TemplateTaxon[]>([]);
  const [result, setResult] = useState<TemplatePage | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const query = useDebounced(q, 250);

  useEffect(() => {
    let active = true;
    Promise.all([templatePermissions(), templateTaxonomy("categories"), templateTaxonomy("tags"), searchTemplates({ scope: "PERSONAL" }), searchTemplates({ scope: "SHARED" })])
      .then(([permissions, cats, labels, personal, shared]) => {
        if (!active) return;
        setCanManageShared(permissions.canManageShared);
        setCategories(cats);
        setTags(labels);
        setCounts({ PERSONAL: personal.total, SHARED: shared.total });
      })
      .catch(() => { if (active) setError(t("settings.could_not_load_templates")); });
    return () => { active = false; };
  }, [version]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    searchTemplates({ scope, q: query, categoryId, tagIds, page })
      .then((data) => { if (active) { setResult(data); setPage(data.page); } })
      .catch(() => { if (active) { setResult(null); setError(t("settings.could_not_load_templates")); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [scope, query, categoryId, tagIds, page, version]);

  function reset() {
    setQ("");
    setCategoryId(null);
    setTagIds([]);
    setPage(1);
  }

  return {
    scope, q, categoryId, tagIds, result, error, loading, counts,
    ready: canManageShared !== null,
    canManageShared: canManageShared === true,
    canManage: scope === "PERSONAL" || canManageShared === true,
    categories: categories.filter((item) => item.scope === scope),
    tags: tags.filter((item) => item.scope === scope),
    allCategories: categories,
    allTags: tags,
    setScope: (next: TemplateScope) => { setScope(next); reset(); },
    setQ: (next: string) => { setQ(next); setPage(1); },
    setCategoryId: (next: number | null) => { setCategoryId(next); setPage(1); },
    setTagIds: (next: number[]) => { setTagIds(next); setPage(1); },
    setPage,
    reset,
    reload: () => setVersion((current) => current + 1),
  };
}

export type TemplateLibraryState = ReturnType<typeof useTemplateLibrary>;
