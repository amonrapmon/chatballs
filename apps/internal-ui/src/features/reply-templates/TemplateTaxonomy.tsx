import { useEffect, useState } from "react";

import { t } from "../../i18n";
import { EmptyState, LoadingState } from "../../shared/ui";
import { fetchReplyTemplates, type ReplyTemplateRef } from "../conversations/model";
import type { TemplateScope } from "./api";
import { TemplateTaxonomyCard } from "./TemplateTaxonomyCard";
import type { TemplateLibraryState } from "./useTemplateLibrary";
import "./taxonomy.css";

// Кадр N7: категории и теги той области, которой сотрудник управляет. Число
// шаблонов считается по всей доступной выдаче, а не по странице библиотеки.

export function TemplateTaxonomy({ library, reload }: { library: TemplateLibraryState; reload: () => void }) {
  const scope: TemplateScope = library.canManage ? library.scope : "PERSONAL";
  const [templates, setTemplates] = useState<ReplyTemplateRef[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetchReplyTemplates()
      .then((items) => { if (active) setTemplates(items); })
      .catch(() => { if (active) setError(t("settings.could_not_load_templates")); });
    return () => { active = false; };
  }, [library.allCategories, library.allTags]);

  if (error) return <EmptyState title={error} />;
  if (!templates) return <LoadingState />;
  return (
    <div className="template-taxonomy">
      <TemplateTaxonomyCard kind="categories" scope={scope} items={library.allCategories.filter((item) => item.scope === scope)} templates={templates} reload={reload} />
      <TemplateTaxonomyCard kind="tags" scope={scope} items={library.allTags.filter((item) => item.scope === scope)} templates={templates} reload={reload} />
    </div>
  );
}
