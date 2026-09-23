import { useEffect, useMemo, useState, type RefObject } from "react";

import { fetchReplyTemplates, type ReplyTemplateRef } from "./model";
import { renderTemplate, type TemplateValues } from "./templateVariables";

// Шаблоны «/» (дизайн-базлайн v2 §9): ввод «/» в начале открывает список,
// продолжение ввода фильтрует по названию. Выбранный шаблон заменяет текст
// поля, переменные подставляются сразу — оператор видит готовый ответ.

export function useComposerTemplates({ text, setText, values, textareaRef }: {
  text: string;
  setText: (text: string) => void;
  values: TemplateValues;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
}) {
  const [templates, setTemplates] = useState<ReplyTemplateRef[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    fetchReplyTemplates().then(setTemplates).catch(() => setTemplates([]));
  }, []);

  const slashQuery = text.startsWith("/") ? text.slice(1).trim().toLowerCase() : null;
  const visible = useMemo(() => {
    if (templates.length === 0) return [];
    if (slashQuery === null) return templates;
    return templates.filter((template) => template.title.toLowerCase().includes(slashQuery));
  }, [templates, slashQuery]);

  function apply(template: ReplyTemplateRef) {
    setText(renderTemplate(template.text, values));
    setOpen(false);
    textareaRef.current?.focus();
  }

  return {
    available: templates.length > 0,
    visible,
    slashQuery,
    menuOpen: open || (slashQuery !== null && visible.length > 0),
    toggle: () => setOpen((current) => !current),
    close: () => setOpen(false),
    apply,
  };
}
