import { useState } from "react";
import { Icon } from "../../shared/icons";
import { SelectMenu } from "../../shared/ui-controls";
import { t } from "../../i18n";
import type { EmailOptions, Mailbox } from "./emailTypes";

export function EmailComposerFields({ options, recipient, mailbox, subject, disabled, onRecipient, onMailbox, onSubject }: {
  options: EmailOptions; recipient: string; mailbox?: Mailbox; subject: string; disabled: boolean;
  onRecipient: (value: string) => void; onMailbox: (id: number) => void; onSubject: (value: string) => void;
}) {
  const [toOpen, setToOpen] = useState(false), [boxOpen, setBoxOpen] = useState(false);
  return <div className="email-composer-fields">
    <div className="email-field-row"><span>{t("mail.recipient")}</span>
      <SelectMenu disabled={disabled} open={toOpen} onOpenChange={setToOpen} selected={[recipient]}
        options={options.addresses.map((value) => ({ value, label: value }))} onSelect={onRecipient}>
        <button type="button" className="row-menu-button email-field-choice" disabled={disabled} aria-label={t("mail.recipient")}>
          <strong>{recipient}</strong><small>{t("mail.saved_address")}</small><Icon name="chevron" size={14} />
        </button>
      </SelectMenu>
    </div>
    <div className="email-field-row"><span>{t("mail.mailbox")}</span>
      <SelectMenu disabled={disabled || !mailbox} open={boxOpen} onOpenChange={setBoxOpen} selected={mailbox ? [String(mailbox.id)] : []}
        options={options.mailboxes.map((box) => ({ value: String(box.id), label: box.name, hint: box.address }))} onSelect={(id) => onMailbox(Number(id))}>
        <button type="button" className={`row-menu-button email-field-choice ${mailbox ? "" : "is-unavailable"}`} disabled={disabled || !mailbox} aria-label={t("mail.mailbox")}>
          <strong>{mailbox?.name ?? t("mail.no_mailbox")}</strong><small>{mailbox?.address}</small><Icon name="chevron" size={14} />
        </button>
      </SelectMenu>
    </div>
    <label className="email-field-row"><span>{t("mail.subject")}</span><input value={subject} maxLength={998} disabled={disabled} aria-label={t("mail.subject")} onChange={(event) => onSubject(event.target.value)} /></label>
  </div>;
}
