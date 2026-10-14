import { Dropdown, type MenuProps } from "antd";
import { Icon } from "../../shared/icons";

export function RuleChips({ label, chips, addLabel, menu, remove, error, disabled, wide = false }: {
  label: string; chips: { key: string; label: string }[]; addLabel: string; menu: MenuProps;
  remove: (key: string) => void; error?: string; disabled: boolean; wide?: boolean;
}) {
  return <div className={`handling-rule-field ${wide ? "handling-rule-wide" : ""}`}>
    <span>{label}</span>
    <div className={`handling-rule-chips ${error ? "is-invalid" : ""}`}>
      {chips.map(chip => <span className="handling-rule-chip" key={chip.key}>{chip.label}
        <button type="button" disabled={disabled} aria-label={chip.label} onClick={() => remove(chip.key)}><Icon name="close" size={11} /></button>
      </span>)}
      <Dropdown overlayClassName="app-dropdown" trigger={["click"]} menu={menu} disabled={disabled}>
        <button className="row-menu-button handling-rule-add" type="button" disabled={disabled}><Icon name="plus" size={12} />{addLabel}</button>
      </Dropdown>
    </div>
    {error && <small className="handling-rule-error" role="alert">{error}</small>}
  </div>;
}
