import type { ComponentProps, ReactNode } from "react";

import { Icon } from "../../shared/icons";
import type { DraftView } from "./replyDraft";
import { t } from "../../i18n";

type IconName = ComponentProps<typeof Icon>["name"];
type ReadyView = Extract<DraftView, { kind: "ready" }>;

// Панель черновика над полем ввода (макет «Чат · состояния», кадры A2–A5, A8).
// Текст черновика живёт в панели, а не в поле: в поле он попадает только по
// «Вставить в ответ», клиенту — только обычной отправкой.
export function ComposerDraftPanel({ view, rejecting, onSelect, onInsert, onRephrase, onRetry, onReject, onDismiss }: {
  view: DraftView;
  rejecting: boolean;
  onSelect: (suggestionId: string) => void;
  onInsert: () => void;
  onRephrase: () => void;
  onRetry: () => void;
  onReject: () => void;
  onDismiss: () => void;
}) {
  if (view.kind === "loading") {
    return (
      <div className="composer-draft">
        <DraftHead icon="sparkles" title={t("conversations.draft_preparing")} note={t("conversations.draft_preparing_source")} />
        <div className="composer-draft-skeleton"><i /><i /><i /></div>
        <div className="composer-draft-actions"><small>{t("conversations.draft_nothing_sent")}</small></div>
      </div>
    );
  }
  if (view.kind === "error") {
    return (
      <div className="composer-draft is-error">
        <DraftHead icon="errorCircle" title={t("conversations.draft_failed")}>
          <CloseButton label={t("common.close")} onClick={onDismiss} />
        </DraftHead>
        <p className="composer-draft-text">{view.reason}</p>
        <div className="composer-draft-actions">
          <DraftAction icon="refresh" label={t("common.try_again")} onClick={onRetry} />
        </div>
      </div>
    );
  }
  return (
    <div className="composer-draft">
      <DraftHead
        icon={view.rephrasing ? "refresh" : "sparkles"}
        title={t("conversations.ai_draft")}
        note={view.rephrasing ? t("conversations.draft_rephrasing") : t("conversations.draft_review_before_sending")}
      >
        <DraftVariants view={view} onSelect={onSelect} />
        <CloseButton label={t("conversations.draft_reject")} disabled={rejecting} onClick={onReject} />
      </DraftHead>
      <p className="composer-draft-text">{view.variants[view.selected].text}</p>
      <div className="composer-draft-actions">
        <DraftAction primary icon="check" label={t("conversations.draft_insert")} onClick={onInsert} />
        {!view.rephrasing && <DraftAction icon="refresh" label={t("conversations.draft_rephrase")} onClick={onRephrase} />}
        <small>{view.rephrasing ? t("conversations.draft_previous_kept") : t("conversations.draft_manual_send_only")}</small>
      </div>
    </div>
  );
}

function DraftHead({ icon, title, note = "", children }: { icon: IconName; title: string; note?: string; children?: ReactNode }) {
  return (
    <div className="composer-draft-head">
      <Icon name={icon} size={14} strokeWidth={1.9} />
      <strong>{title}</strong>
      <small>{note}</small>
      {children}
    </div>
  );
}

// Переключатель вариантов: один вариант его не показывает, а пока готовится
// следующий — к номерам добавляется «…».
function DraftVariants({ view, onSelect }: { view: ReadyView; onSelect: (suggestionId: string) => void }) {
  const total = view.variants.length;
  if (total < 2 && !view.rephrasing) return null;
  return (
    <span className="composer-draft-variants">
      {view.variants.map((variant, index) => (
        <button
          key={variant.id}
          className={index === view.selected ? "is-active" : undefined}
          title={view.rephrasing ? t("conversations.draft_variant", { index: index + 1 }) : t("conversations.draft_variant_of", { index: index + 1, total })}
          type="button"
          onClick={() => onSelect(variant.id)}
        >{index + 1}</button>
      ))}
      {view.rephrasing && <span className="is-pending" title={t("conversations.draft_variant_pending")}>…</span>}
    </span>
  );
}

function DraftAction({ icon, label, primary = false, onClick }: { icon: IconName; label: string; primary?: boolean; onClick: () => void }) {
  return (
    <button className={`composer-draft-action${primary ? " is-primary" : ""}`} type="button" onClick={onClick}>
      <Icon name={icon} size={13} strokeWidth={2} />{label}
    </button>
  );
}

function CloseButton({ label, disabled = false, onClick }: { label: string; disabled?: boolean; onClick: () => void }) {
  return (
    <button className="composer-draft-close" aria-label={label} title={label} type="button" disabled={disabled} onClick={onClick}>
      <Icon name="close" size={13} strokeWidth={2.2} />
    </button>
  );
}
