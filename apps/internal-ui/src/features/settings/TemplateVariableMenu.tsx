import { Dropdown } from "antd";

import { Icon } from "../../shared/icons";
import { TEMPLATE_VARIABLES, TEMPLATE_VARIABLE_LABEL, type TemplateVariable } from "../conversations/templateVariables";
import { t } from "../../i18n";

// «Вставить переменную» в окне шаблона ответа: коды переменных не нужно
// помнить — пункт меню вставляет его в позицию курсора.

export function TemplateVariableMenu({ onPick }: { onPick: (variable: TemplateVariable) => void }) {
  const items = TEMPLATE_VARIABLES.map((variable) => ({
    key: variable,
    label: t(TEMPLATE_VARIABLE_LABEL[variable]),
    onClick: () => onPick(variable),
  }));
  return (
    <Dropdown menu={{ items }} trigger={["click"]} placement="bottomLeft" overlayClassName="app-dropdown">
      <button className="link has-icon template-variable-trigger" type="button">
        <Icon name="plus" size={13} strokeWidth={2.2} />{t("settings.insert_variable")}
      </button>
    </Dropdown>
  );
}
