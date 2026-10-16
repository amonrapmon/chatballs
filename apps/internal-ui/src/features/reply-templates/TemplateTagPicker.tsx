import { useRef, useState } from "react";

import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { SelectMenu } from "../../shared/ui-controls";
import type { TemplateTaxon } from "./api";

// Поле «Теги» окна шаблона (кадр N5): выбранные теги — чипами с крестиком,
// «Добавить тег» открывает общий список с галочками. Сами теги создаются на
// странице «Категории и теги».

export function TemplateTagPicker({ tags, value, onChange }: {
  tags: TemplateTaxon[];
  value: number[];
  onChange: (value: number[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [menuWidth, setMenuWidth] = useState<number>();
  const box = useRef<HTMLDivElement>(null);
  const toggle = (id: number) => onChange(value.includes(id) ? value.filter((item) => item !== id) : [...value, id]);
  return (
    <div className="readonly-field wide">
      <span>{t("templates.tags")}</span>
      <SelectMenu
        multiple
        disabled={tags.length === 0}
        open={open}
        onOpenChange={setOpen}
        options={tags.map((tag) => ({ value: String(tag.id), label: `# ${tag.name}` }))}
        selected={value.map(String)}
        overlayClassName="app-dropdown is-field"
        overlayStyle={menuWidth ? { width: menuWidth } : undefined}
        onSelect={(id) => toggle(Number(id))}
      >
        <div
          className={`template-tag-box ${tags.length === 0 ? "is-disabled" : ""}`.trim()}
          ref={box}
          role="button"
          tabIndex={0}
          aria-label={t("templates.tags")}
          onClick={() => setMenuWidth(box.current?.offsetWidth)}
          onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setMenuWidth(box.current?.offsetWidth); setOpen(true); } }}
        >
          {tags.filter((tag) => value.includes(tag.id)).map((tag) => (
            <span className="template-tag-pill" key={tag.id}>
              # {tag.name}
              <button type="button" aria-label={t("templates.remove_tag", { name: tag.name })} onClick={(event) => { event.stopPropagation(); toggle(tag.id); }}>
                <Icon name="close" size={11} strokeWidth={2.4} />
              </button>
            </span>
          ))}
          <span className="template-tag-add">{t("templates.add_tag")}</span>
        </div>
      </SelectMenu>
    </div>
  );
}
