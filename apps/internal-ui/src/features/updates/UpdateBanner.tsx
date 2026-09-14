import { useState } from "react";

import { DecisionDialog } from "../../shared/DecisionDialog";
import { Icon, LogoSpinner } from "../../shared/icons";
import { Button } from "../../shared/ui-controls";
import { installUpdate, type UpdateInfo } from "./api";
import { useUpdatesCardVisible } from "./cardPresence";
import { STAGES, clockLabel, stageNumber, stageOf, stageProgress, useElapsed } from "./progress";
import { useUpdateInfo } from "./useUpdateInfo";
import { t } from "../../i18n";

// Полоса поверх рабочей области у администратора установки: есть новая
// версия, идёт установка, установка завершена или сорвалась. Та же полоса,
// что у установки демо-данных (ADR-CHATBALLS-0049).

export function UpdateBanner({ enabled }: { enabled: boolean }) {
  const { info, setInfo, installing, unreachable, finished, forget, markPending, targetVersion, startedAt } =
    useUpdateInfo(enabled);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errorText, setErrorText] = useState("");
  const cardVisible = useUpdatesCardVisible();

  // Карточка «Обновления» открыта — она и рассказывает всё то же самое.
  if (!enabled || cardVisible) return null;

  async function install() {
    setBusy(true);
    setErrorText("");
    // Полоса хода появляется по нажатию, а не по ответу сервера: запрос идёт
    // около секунды, и всё это время экран не должен выглядеть безучастным.
    markPending(info?.latestVersion ?? null);
    try {
      setInfo(await installUpdate());
      setConfirming(false);
    } catch (error) {
      forget();
      setErrorText(error instanceof Error ? error.message : t("common.could_not_complete_action"));
    } finally {
      setBusy(false);
    }
  }

  const version = targetVersion ?? info?.latestVersion ?? "";

  if (installing) {
    return (
      <UpdateBannerProgress info={info} unreachable={unreachable} version={version} startedAt={startedAt} />
    );
  }

  if (finished) {
    const installed = info?.currentVersion ?? version;
    return (
      <div className="demo-install-banner update-banner is-done">
        <Icon name="check" size={15} strokeWidth={2.2} />
        <span>{t("updates.done", { version: installed })}</span>
        <button type="button" onClick={() => window.location.reload()}>{t("updates.reload")}</button>
        <button className="demo-install-close" type="button" onClick={forget} aria-label={t("common.hide")}>
          <Icon name="close" size={14} strokeWidth={2} />
        </button>
      </div>
    );
  }

  if (info?.install.status === "FAILED" && dismissed !== `failed:${version}`) {
    return (
      <div className="demo-install-banner update-banner is-failed">
        <Icon name="warning" size={15} strokeWidth={2} />
        <span>{t("updates.failed", { version })}{info.install.message ? `: ${info.install.message}` : ""}</span>
        <button className="demo-install-close" type="button" onClick={() => setDismissed(`failed:${version}`)} aria-label={t("common.hide")}>
          <Icon name="close" size={14} strokeWidth={2} />
        </button>
      </div>
    );
  }

  if (!info?.available || dismissed === `available:${info.latestVersion}`) return null;

  return (
    <>
      <div className="demo-install-banner update-banner">
        <Icon name="download" size={15} strokeWidth={2} />
        <span>
          {t("updates.available_title", { version: info.latestVersion ?? "" })}
          {!info.updaterOnline && ` · ${t("updates.updater_offline")}`}
        </span>
        {info.latestPageUrl && (
          <a className="link is-neutral" href={info.latestPageUrl} target="_blank" rel="noreferrer">{t("updates.whats_new")}</a>
        )}
        <button type="button" disabled={!info.updaterOnline} onClick={() => setConfirming(true)}>{t("updates.install")}</button>
        <button className="demo-install-close" type="button" onClick={() => setDismissed(`available:${info.latestVersion}`)} aria-label={t("common.hide")}>
          <Icon name="close" size={14} strokeWidth={2} />
        </button>
      </div>
      <DecisionDialog
        open={confirming}
        tone="warning"
        icon="download"
        title={t("updates.confirm_title", { version: info.latestVersion ?? "" })}
        description={errorText || t("updates.confirm_text")}
        onClose={() => setConfirming(false)}
        actions={(
          <>
            <Button variant="secondary" disabled={busy} onClick={() => setConfirming(false)}>{t("common.cancel")}</Button>
            <Button variant="primary" disabled={busy} onClick={() => void install()}>{t("updates.install")}</Button>
          </>
        )}
      />
    </>
  );
}

// Ход установки в полосе: место есть только на одну строку, поэтому шаги
// сворачиваются в тонкую линию с подписью «шаг N из M» и временем — то же
// знание, что и в списке шагов карточки «Обновления».

function UpdateBannerProgress({
  info,
  unreachable,
  version,
  startedAt,
}: {
  info: UpdateInfo | null;
  unreachable: boolean;
  version: string;
  startedAt: string | null;
}) {
  const stage = stageOf(info, unreachable);
  const elapsed = useElapsed(startedAt, true);

  return (
    <div
      className="demo-install-banner update-banner"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={STAGES.length}
      aria-valuenow={stageNumber(stage)}
      aria-valuetext={`${t("updates.installing", { version })} ${t(`updates.stage_${stage}`)}`}
    >
      <LogoSpinner size={17} />
      <span>
        {t("updates.installing", { version })} {t(`updates.stage_${stage}`)}
      </span>
      <span className="update-banner-bar" aria-hidden="true">
        <span style={{ width: `${stageProgress(stage)}%` }} />
      </span>
      <span className="update-banner-step">
        {t("updates.progress_step", { step: String(stageNumber(stage)), total: String(STAGES.length) })} · {clockLabel(elapsed)}
      </span>
    </div>
  );
}
