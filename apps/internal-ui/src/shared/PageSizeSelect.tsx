import { useState } from "react";

import { Icon } from "./icons";
import { SelectMenu } from "./ui-controls";
import { PAGE_SIZE_OPTIONS } from "./usePageSize";
import { t } from "../i18n";

// «На странице: 20» в подвале списка. Отдельный селект приложения заводить не
// надо: это тот же `SelectMenu`, только с компактным триггером подвала.

export function PageSizeSelect({ value, onChange, options = PAGE_SIZE_OPTIONS }: {
  value: number;
  onChange: (pageSize: number) => void;
  options?: number[];
}) {
  const [open, setOpen] = useState(false);
  return (
    <SelectMenu
      open={open}
      options={options.map((size) => ({ value: String(size), label: String(size) }))}
      overlayClassName="app-dropdown is-pager-size"
      selected={[String(value)]}
      onOpenChange={setOpen}
      onSelect={(next) => {
        setOpen(false);
        onChange(Number(next));
      }}
    >
      <button className="pager-size" type="button">
        <i>{t("shared.per_page")}</i>
        {value}
        <Icon name="chevron" size={12} strokeWidth={2.2} />
      </button>
    </SelectMenu>
  );
}
