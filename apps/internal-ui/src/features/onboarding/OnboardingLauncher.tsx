import { Icon } from "../../shared/icons";
import { useDraggablePosition } from "../../shared/useDraggablePosition";
import { t } from "../../i18n";
import { useOnboarding } from "./useOnboarding";

// Пилюля возврата в правом нижнем углу рабочей области. Появляется, когда
// окно закрыто, тур не идёт, а настроено ещё не всё: закрыть онбординг можно
// одним кликом, но дорогу назад стоит оставить на виду.
//
// Пилюлю перетаскивают: в правом нижнем углу она закрывает то кнопку отправки,
// то последнее сообщение ленты. Место, куда её отвели, помнит браузер.

export function OnboardingLauncher() {
  const onboarding = useOnboarding();
  const drag = useDraggablePosition<HTMLButtonElement>("onboarding-launcher", { right: 24, bottom: 24 });
  if (!onboarding?.showLauncher) return null;
  return (
    <button
      className={`ob-launcher${drag.dragging ? " is-dragging" : ""}`}
      ref={drag.ref}
      style={drag.style}
      type="button"
      onPointerDown={drag.onPointerDown}
      onClick={() => { if (!drag.wasDragged()) onboarding.open(); }}
    >
      <Icon name="sparkles" size={17} strokeWidth={1.9} />
      {t("onboarding.title")}
      <small>{t("onboarding.progress_short", { done: onboarding.doneCount, total: onboarding.steps.length })}</small>
    </button>
  );
}
