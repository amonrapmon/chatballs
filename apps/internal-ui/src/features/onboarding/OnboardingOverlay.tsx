import { useEffect, useRef } from "react";

import { Icon, LogoIcon } from "../../shared/icons";
import { t } from "../../i18n";
import type { OnboardingStep } from "./steps";
import { useOnboarding, type OnboardingApi } from "./useOnboarding";

// Окно онбординга: приветствие, визард шагов и финальный экран.
//
// Размеры, зазоры и толщины обводок иконок взяты из дизайн-референса
// `design/baseline/Онбординг` — сверяться нужно с ним, а не с соседними
// экранами рабочего места.
//
// Окно живёт внутри `.hub-shell`, а не в портале на body: тур подсвечивает
// элементы приложения теми же координатами от корня, и держать оба слоя в
// одной системе отсчёта проще, чем сводить две.

const FOCUSABLE = 'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

/** Ловушка фокуса и клавиши: Tab по кругу, Esc закрывает, ←/→ листают шаги. */
function useModalKeys(active: boolean, onboarding: OnboardingApi | null, cardRef: React.RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    if (!active || !onboarding) return;
    cardRef.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
  }, [active, onboarding, cardRef]);

  useEffect(() => {
    if (!active || !onboarding) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onboarding.dismiss();
        return;
      }
      if (onboarding.view === "steps" && (event.key === "ArrowRight" || event.key === "ArrowLeft")) {
        const target = event.target as HTMLElement | null;
        // Стрелки внутри поля ввода принадлежат полю, а не визарду.
        if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
        event.preventDefault();
        onboarding.goTo(onboarding.index + (event.key === "ArrowRight" ? 1 : -1));
        return;
      }
      if (event.key !== "Tab") return;
      const items = [...(cardRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])].filter((item) => item.offsetParent !== null);
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, onboarding, cardRef]);
}

export function OnboardingOverlay() {
  const onboarding = useOnboarding();
  const cardRef = useRef<HTMLDivElement>(null);
  const visible = Boolean(onboarding && onboarding.view !== null && onboarding.tourIndex === null);
  useModalKeys(visible, onboarding, cardRef);

  if (!onboarding || !visible) return null;
  if (onboarding.view === "welcome") return <WelcomeView onboarding={onboarding} cardRef={cardRef} />;
  if (onboarding.view === "done") return <DoneView onboarding={onboarding} cardRef={cardRef} />;
  return <StepsView onboarding={onboarding} cardRef={cardRef} />;
}

/** В приветствии крестик лежит поверх градиентной шапки, в визарде стоит в
 *  строке рядом с чипом шага. */
function CloseButton({ floating = false, onClick }: { floating?: boolean; onClick: () => void }) {
  return (
    <button className={`ob-close ${floating ? "is-floating" : ""}`} type="button" aria-label={t("common.close")} title={t("common.close")} onClick={onClick}>
      <Icon name="close" size={17} strokeWidth={1.8} />
    </button>
  );
}

function WelcomeView({ onboarding, cardRef }: { onboarding: OnboardingApi; cardRef: React.RefObject<HTMLDivElement | null> }) {
  return (
    <div className="ob-overlay is-welcome">
      <div className="ob-card ob-welcome" ref={cardRef} role="dialog" aria-modal="true" aria-labelledby="ob-welcome-title">
        <div className="ob-welcome-head">
          <CloseButton floating onClick={onboarding.dismiss} />
          <span className="ob-logo-tile"><LogoIcon size={28} /></span>
          <p className="ob-eyebrow">{t("onboarding.eyebrow")}</p>
          <h2 id="ob-welcome-title">{onboarding.welcomeTitle}</h2>
          <p>{t("onboarding.welcome_lead")}</p>
        </div>
        <div className="ob-facts">
          <div><strong>{t("onboarding.fact_time")}</strong><small>{t("onboarding.fact_time_note")}</small></div>
          <div><strong>{t("onboarding.fact_key")}</strong><small>{t("onboarding.fact_key_note")}</small></div>
          <div><strong>{t("onboarding.fact_data")}</strong><small>{t("onboarding.fact_data_note")}</small></div>
        </div>
        <div className="ob-welcome-foot">
          <button className="ob-text-button" type="button" onClick={onboarding.dismiss}>{t("onboarding.later")}</button>
          <button className="ob-primary is-welcome" type="button" onClick={onboarding.startSteps}>
            {t("onboarding.start")}
            <Icon name="arrow" size={17} strokeWidth={1.9} />
          </button>
        </div>
      </div>
    </div>
  );
}

function StepsView({ onboarding, cardRef }: { onboarding: OnboardingApi; cardRef: React.RefObject<HTMLDivElement | null> }) {
  const { steps, index, doneCount } = onboarding;
  const step = steps[index];
  if (!step) return null;
  const total = steps.length;
  const percent = Math.round((doneCount / total) * 100);
  const last = index === total - 1;

  return (
    <div className="ob-overlay is-steps">
      <div className="ob-card ob-steps" ref={cardRef} role="dialog" aria-modal="true" aria-labelledby="ob-step-title">
        <aside className="ob-rail">
          <div className="ob-rail-head">
            <div className="ob-rail-brand"><span><LogoIcon size={22} /></span><strong>{t("onboarding.title")}</strong></div>
            <div className="ob-rail-progress-row">
              <span>{t("onboarding.progress", { done: doneCount, total })}</span>
              <small>{percent}%</small>
            </div>
            <div className="ob-rail-bar"><i style={{ width: `${percent}%` }} /></div>
          </div>
          <ol className="ob-rail-list" aria-label={t("onboarding.steps_list")}>
            {steps.map((item, position) => (
              <li key={item.key}>
                <button
                  className={`ob-rail-step ${position === index ? "is-current" : ""} ${onboarding.state.steps[item.key] ? "is-done" : ""}`}
                  type="button"
                  aria-current={position === index ? "step" : undefined}
                  onClick={() => onboarding.goTo(position)}
                >
                  <span className="ob-rail-mark">
                    {onboarding.state.steps[item.key] ? <Icon name="check" size={11} strokeWidth={2.6} /> : position + 1}
                  </span>
                  <span className="ob-rail-name">{item.name}</span>
                  <small>{item.time}</small>
                </button>
              </li>
            ))}
          </ol>
          <div className="ob-rail-foot">
            <button className="ob-text-button" type="button" onClick={onboarding.dismiss}>{t("onboarding.close_and_self")}</button>
          </div>
        </aside>
        <div className="ob-body">
          <header className="ob-body-head">
            <span className="ob-chip is-accent">{t("onboarding.step_of", { index: index + 1, total, time: step.time })}</span>
            <CloseButton onClick={onboarding.dismiss} />
          </header>
          {/* На узком экране рейка скрыта — полоса прогресса остаётся здесь. */}
          <div className="ob-rail-bar ob-narrow-bar"><i style={{ width: `${percent}%` }} /></div>
          <div className="ob-body-scroll">
            <h2 id="ob-step-title">{step.title}</h2>
            <p className="ob-lead">{step.lead}</p>
            <div className="ob-path">
              {step.path.map((crumb, position) => (
                <span className="ob-crumb" key={crumb}>
                  {crumb}
                  {position < step.path.length - 1 && <Icon name="chevronRight" size={12} strokeWidth={2} />}
                </span>
              ))}
            </div>
            <ol className="ob-instructions">
              {step.instructions.map((line, position) => (
                <li key={line}><span>{position + 1}</span><span>{line}</span></li>
              ))}
            </ol>
            <div className="ob-warning">
              <Icon name="alert" size={16} strokeWidth={1.9} />
              <p>{step.warning}</p>
            </div>
            <StepPreview step={step} />
          </div>
          <footer className="ob-body-foot">
            <button className="ob-ghost" type="button" onClick={onboarding.back}>
              <Icon name="chevronLeft" size={16} strokeWidth={1.9} />
              {t("onboarding.back")}
            </button>
            <div className="ob-body-actions">
              <button className="ob-secondary" type="button" onClick={onboarding.showTour}>
                <Icon name="eye" size={16} strokeWidth={1.9} />
                {t("onboarding.show_where")}
              </button>
              <button className="ob-secondary" type="button" onClick={onboarding.openSection}>{t("onboarding.open_section")}</button>
              <button className="ob-primary" type="button" onClick={onboarding.next}>
                {last ? t("onboarding.finish") : t("onboarding.next")}
                <Icon name="arrow" size={16} strokeWidth={1.9} />
              </button>
            </div>
          </footer>
        </div>
      </div>
    </div>
  );
}

function StepPreview({ step }: { step: OnboardingStep }) {
  const { preview } = step;
  return (
    <div className="ob-preview">
      <div className="ob-preview-head">
        <span className="ob-preview-label"><i />{preview.label}</span>
        <span className={`ob-chip ${preview.tone === "success" ? "is-success" : "is-waiting"}`}>
          {preview.tone === "success" && <Icon name="check" size={11} strokeWidth={2.6} />}
          {preview.chip}
        </span>
      </div>
      <div className="ob-preview-rows">
        {preview.rows.map((row) => (
          <div className="ob-preview-row" key={row.label}>
            <span>{row.label}</span>
            <b>{row.value}</b>
          </div>
        ))}
      </div>
      {preview.code && <div className="ob-preview-code"><code>{preview.code}</code></div>}
    </div>
  );
}

function DoneView({ onboarding, cardRef }: { onboarding: OnboardingApi; cardRef: React.RefObject<HTMLDivElement | null> }) {
  return (
    <div className="ob-overlay is-done">
      <div className="ob-card ob-done" ref={cardRef} role="dialog" aria-modal="true" aria-labelledby="ob-done-title">
        <div className="ob-done-head">
          <span className="ob-logo-tile is-success"><Icon name="check" size={24} strokeWidth={2.4} /></span>
          <h2 id="ob-done-title">{t("onboarding.done_title")}</h2>
          <p>{t("onboarding.done_lead")}</p>
        </div>
        <div className="ob-summary">
          {onboarding.steps.map((step) => (
            <div className={`ob-summary-item ${onboarding.state.steps[step.key] ? "is-done" : ""}`} key={step.key}>
              <span>{onboarding.state.steps[step.key] && <Icon name="check" size={10} strokeWidth={2.8} />}</span>
              <span>{step.name}</span>
            </div>
          ))}
        </div>
        <div className="ob-done-foot">
          <button className="ob-text-button" type="button" onClick={onboarding.restart}>{t("onboarding.restart")}</button>
          <button className="ob-primary is-done" type="button" onClick={onboarding.completeToChat}>
            {t("onboarding.go_chat")}
            <Icon name="arrow" size={17} strokeWidth={1.9} />
          </button>
        </div>
      </div>
    </div>
  );
}
