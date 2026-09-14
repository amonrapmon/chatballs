import { Icon, LogoSpinner } from "../../shared/icons";
import type { UpdateInfo } from "./api";
import { STAGES, clockLabel, stageNumber, stageOf, useElapsed } from "./progress";
import { t } from "../../i18n";

// Ход установки списком шагов. Сколько времени займёт обновление, заранее не
// знает никто (образы тянутся с разной скоростью), поэтому полосы с процентами
// здесь нет: человеку показывается, какой шаг идёт сейчас, сколько их всего и
// сколько уже идёт установка. Этого достаточно, чтобы понять, что всё живо.

export function UpdateProgress({
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
  const current = stageNumber(stage);
  const elapsed = useElapsed(startedAt, true);

  return (
    <div className="update-progress" role="status" aria-live="polite">
      <div className="update-progress-head">
        <LogoSpinner size={18} />
        <strong>{t("updates.progress_title", { version })}</strong>
        <span className="update-progress-clock">
          {t("updates.progress_step", { step: String(current), total: String(STAGES.length) })} · {clockLabel(elapsed)}
        </span>
      </div>
      <ol className="update-progress-steps">
        {STAGES.map((item, index) => {
          const state = index + 1 < current ? "is-done" : index + 1 === current ? "is-current" : "is-waiting";
          return (
            <li key={item} className={`update-progress-step ${state}`}>
              <span className="update-progress-mark" aria-hidden="true">
                {state === "is-done" && <Icon name="check" size={11} strokeWidth={2.6} />}
              </span>
              <span>{t(`updates.step_${item}`)}</span>
            </li>
          );
        })}
      </ol>
      <p className="update-progress-hint">{t("updates.progress_hint")}</p>
    </div>
  );
}
