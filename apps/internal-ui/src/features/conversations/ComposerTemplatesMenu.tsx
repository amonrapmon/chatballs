import { useEffect, useRef } from "react";

import { t } from "../../i18n";
import { SearchInput } from "../../shared/ui-controls";
import { TemplateScopeTabs } from "../reply-templates/TemplateScopeTabs";
import type { ComposerTemplatesState } from "./useComposerTemplates";

// Меню выбора шаблона (кадры T1, T2): поиск по названию и тексту, области
// «Все · Личные · Общие», строки с областью и категорией, подсказка клавиш.

export function ComposerTemplatesMenu({ templates }: { templates: ComposerTemplatesState }) {
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Открыли кнопкой — печатают сразу в поиске; при «/» фокус остаётся в поле
  // сообщения, запрос набирают там.
  useEffect(() => {
    if (templates.slashQuery === null) searchRef.current?.focus();
  }, []);

  useEffect(() => {
    listRef.current?.querySelector(".is-active")?.scrollIntoView({ block: "nearest" });
  }, [templates.selected]);

  return (
    <div
      className="reply-template-picker"
      onKeyDown={(event) => {
        if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); templates.escape(); }
        if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); templates.move(event.key === "ArrowDown" ? 1 : -1); }
        if (event.key === "Enter") { event.preventDefault(); templates.applySelected(); }
      }}
    >
      <div className="reply-template-picker-toolbar">
        <SearchInput inputRef={searchRef} placeholder={t("templates.search")} value={templates.query} onChange={templates.setQuery} />
        <TemplateScopeTabs value={templates.scope} onChange={templates.setScope} all />
      </div>
      <div
        className="reply-template-picker-items"
        ref={listRef}
        role="listbox"
        aria-label={t("settings.reply_templates")}
        onScroll={(event) => {
          const node = event.currentTarget;
          if (node.scrollTop + node.clientHeight >= node.scrollHeight - 30) void templates.loadMore();
        }}
      >
        {templates.visible.map((item, index) => (
          <button
            key={item.id}
            type="button"
            role="option"
            aria-selected={index === templates.selected}
            className={index === templates.selected ? "is-active" : ""}
            disabled={templates.applying}
            onClick={() => void templates.apply(item)}
          >
            <span>
              <strong>{item.title}</strong>
              <b className={item.scope === "PERSONAL" ? "is-personal" : ""}>{t(item.scope === "PERSONAL" ? "templates.personal_one" : "templates.shared_one")}</b>
              <small>{templates.categories.find((category) => category.id === item.categoryId)?.name ?? t("templates.no_category")}</small>
            </span>
            <small>{item.text.replace(/\s+/g, " ")}</small>
          </button>
        ))}
        {!templates.loading && templates.visible.length === 0 && <p>{templates.error || t("templates.empty_search")}</p>}
      </div>
      <footer>
        <span>{t("templates.choose_keys")}</span>
        <span>{t("templates.insert_keys")}</span>
        <span>{t("templates.close_keys")}</span>
      </footer>
    </div>
  );
}
