import type { AgentRef } from "../agents/model";
import { t } from "../../i18n";
import { recipientName } from "./model";
import { RuleChips } from "./RuleChips";
import type { HandlingRule, Recipient, RuleErrors } from "./types";

export function RuleFields({ rule, channels, change, errors, busy }: {
  rule: HandlingRule; channels: AgentRef[]; change: (rule: HandlingRule) => void; errors: RuleErrors; busy: boolean;
}) {
  const selected = rule.conditions.channelIds ?? [];
  const channelEnabled = rule.catalog.conditions.includes("channelIds");
  const availableEnabled = rule.catalog.conditions.includes("availableOnly");
  const setChannels = (channelIds: number[]) => change({ ...rule, conditions: { ...rule.conditions, channelIds } });
  const conditionChips = [
    ...selected.map(id => ({ key: String(id), label: t("handling_rules.channel_chip", { name: channels.find(item => item.id === id)?.name ?? String(id) }) })),
    ...(rule.conditions.availableOnly ? [{ key: "availableOnly", label: t("handling_rules.available_only") }] : []),
  ];
  return <div className="handling-rule-fields">
    <p className="handling-rule-help">{t(`handling_rules.help_${rule.kind}`)}</p>
    {(channelEnabled || availableEnabled) && <RuleChips wide label={t("handling_rules.conditions")} chips={conditionChips} addLabel={t("handling_rules.condition")}
      disabled={busy} error={errors.conditions} remove={key => key === "availableOnly"
        ? change({ ...rule, conditions: { ...rule.conditions, availableOnly: false } }) : setChannels(selected.filter(id => id !== Number(key)))}
      menu={{ items: [
        ...(channelEnabled ? [{ key: "channels", label: t("handling_rules.channel"), children: channels.map(channel => ({ key: String(channel.id), label: channel.name, disabled: selected.includes(channel.id) })) }] : []),
        ...(availableEnabled ? [{ key: "availableOnly", label: t("handling_rules.available_only"), disabled: !!rule.conditions.availableOnly }] : []),
      ], onClick: ({ key }) => key === "availableOnly" ? change({ ...rule, conditions: { ...rule.conditions, availableOnly: true } }) : setChannels([...selected, Number(key)]) }}
      help={t(availableEnabled ? "handling_rules.conditions_help" : "handling_rules.agents_help")} />}
    <label className="handling-rule-field"><span>{t(`handling_rules.delay_${rule.kind}`)}</span>
      <span className={`handling-rule-minutes ${errors.delayMinutes ? "is-invalid" : ""}`}>
        <input aria-label={t(`handling_rules.delay_${rule.kind}`)} type="number" min={1} max={rule.catalog.maxDelayMinutes} step={1} disabled={busy}
          value={rule.delayMinutes ?? ""} aria-invalid={!!errors.delayMinutes}
          onChange={event => change({ ...rule, delayMinutes: event.target.value === "" ? null : Number(event.target.value) })} />
        <small>{t("handling_rules.minutes")}</small>
      </span>{errors.delayMinutes && <small className="handling-rule-error" role="alert">{errors.delayMinutes}</small>}
    </label>
    {!rule.catalog.requiresText && <RuleChips label={t("handling_rules.recipients")} chips={rule.recipients.map(value => ({ key: value, label: recipientName(value) }))}
        addLabel={t("handling_rules.recipient")} disabled={busy} error={errors.recipients}
        remove={key => change({ ...rule, recipients: rule.recipients.filter(value => value !== key) })}
        menu={{ items: rule.catalog.recipients.map(value => ({ key: value, label: recipientName(value), disabled: rule.recipients.includes(value) })),
          onClick: ({ key }) => change({ ...rule, recipients: [...rule.recipients, key as Recipient] }) }}
        help={t("handling_rules.recipients_help")} />}
    {rule.catalog.requiresText && <label className="handling-rule-field handling-rule-wide"><span>{t("handling_rules.text")}</span>
      <textarea rows={3} maxLength={rule.catalog.maxTextLength} disabled={busy} value={rule.text} aria-invalid={!!errors.text}
        onChange={event => change({ ...rule, text: event.target.value })} />
      {errors.text && <small className="handling-rule-error" role="alert">{errors.text}</small>}
      <small>{t("handling_rules.text_help", { deadline: rule.catalog.deadlinePlaceholder })}</small>
    </label>}
    {errors.detail && <p className="handling-rule-error" role="alert">{errors.detail}</p>}
  </div>;
}
