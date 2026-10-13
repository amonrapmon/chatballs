import { fmt, t, tn } from "../../../i18n";
import { Icon } from "../../../shared/icons";
import { Button } from "../../../shared/ui-controls";
import { Pagination } from "../../../shared/Pagination";
import { LoadingState } from "../../../shared/ui";
import { useTransferReasons } from "./useTransferReasons";

export function TransferReasonsCard() {
  const state = useTransferReasons();
  const { list, busy } = state;
  return <section className="transfer-settings-card">
    <header><h3>{t("transfers.reasons_title")}</h3><p>{t("transfers.reasons_lead")}</p></header>
    <div className="transfer-reasons-table">
      <div className="transfer-reason-row is-heading">
        {[t("transfers.name"), t("transfers.used"), t("transfers.status"), ""].map((label, i) => <span key={i}>{label}</span>)}
      </div>
      {list.loading && !list.payload && <LoadingState />}
      {list.errorText && <p className="transfer-error">{list.errorText}</p>}
      {list.items.map((reason) => <div className={`transfer-reason-row ${reason.isActive ? "" : "is-disabled"} ${state.editing === reason.id ? "is-editing" : ""}`} key={reason.id}>
        <div>
          {state.editing === reason.id
            ? <input aria-label={t("transfers.name")} value={state.draft} maxLength={120} disabled={busy} className={state.errorId === reason.id && state.error ? "is-invalid" : ""} onChange={(e) => state.setDraft(e.target.value)} />
            : <><strong>{reason.name}</strong>
              {reason.renamedAt && reason.previousName && <small>{t("transfers.renamed", { date: fmt.shortDate(reason.renamedAt), name: reason.previousName })}</small>}
              {!reason.isActive && <small>{t("transfers.disabled_hint")}</small>}</>}
          {state.errorId === reason.id && state.error && <small className="transfer-error">{state.error}</small>}
        </div>
        <span>{tn("transfers.count", reason.usageCount)}</span>
        <span><b className={`transfer-reason-status ${reason.isActive ? "is-active" : ""}`}>{t(reason.isActive ? "transfers.active" : "transfers.disabled")}</b></span>
        <div className="transfer-row-actions">
          {state.editing === reason.id ? <>
            <Button variant="secondary" disabled={busy} onClick={state.cancel}>{t("common.cancel")}</Button>
            <Button variant="primary" disabled={busy} onClick={() => void state.save()}>{t("common.save")}</Button>
          </> : <>
            {reason.isActive && <button className="row-menu-button" type="button" title={t("transfers.rename")} disabled={busy} onClick={() => state.edit(reason.id, reason.name)}><Icon name="edit" size={14} /></button>}
            <button className="link is-muted" type="button" disabled={busy} onClick={() => void state.toggle(reason.id, !reason.isActive)}>{t(reason.isActive ? "transfers.disable" : "transfers.enable")}</button>
          </>}
        </div>
      </div>)}
    </div>
    <form className="transfer-reason-create" onSubmit={(e) => { e.preventDefault(); void state.create(); }}>
      <div><input aria-label={t("transfers.new_name")} placeholder={t("transfers.new_name")} value={state.newName} maxLength={120} disabled={busy} onChange={(e) => state.setNewName(e.target.value)} />
        {state.errorId === null && state.error && <small className="transfer-error">{state.error}</small>}</div>
      <Button variant="secondary" type="submit" icon="plus" disabled={busy}>{t("transfers.create")}</Button>
    </form>
    {list.pageCount > 1 && <Pagination page={list.page} pageCount={list.pageCount} onPage={list.setPage} />}
    <p className="transfer-settings-note">{t("transfers.reasons_note")}</p>
  </section>;
}
