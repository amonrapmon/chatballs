import { useState } from "react";

import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { SelectMenu } from "../../shared/ui-controls";
import type { TemplateVariable } from "./api";

// «Вставить переменную» в окне шаблона ответа (кадр N5): список приходит из
// серверного каталога, пункт вставляет маркер в позицию курсора. У
// дополнительного поля второй строкой — подключение, которому оно принадлежит.

export function TemplateVariableMenu({ variables, onPick }: { variables: TemplateVariable[]; onPick: (variable: TemplateVariable) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <SelectMenu
      disabled={variables.length === 0}
      open={open}
      onOpenChange={setOpen}
      options={variables.map((variable) => ({ value: variable.key, label: variable.label, hint: variable.connectionName }))}
      selected={[]}
      placement="bottomRight"
      onSelect={(key) => {
        const variable = variables.find((item) => item.key === key);
        setOpen(false);
        if (variable) onPick(variable);
      }}
    >
      {/* Фокус остаётся в тексте шаблона: меню вставляет в позицию курсора. */}
      <button className="link has-icon" type="button" disabled={variables.length === 0} onMouseDown={(event) => event.preventDefault()}>
        <Icon name="plus" size={13} strokeWidth={2.2} />{t("settings.insert_variable")}
      </button>
    </SelectMenu>
  );
}
