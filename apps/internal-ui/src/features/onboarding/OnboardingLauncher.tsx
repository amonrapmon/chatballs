import { Icon } from "../../shared/icons";
import { t } from "../../i18n";
import { useOnboarding } from "./useOnboarding";

// Пилюля возврата в правом нижнем углу рабочей области. Появляется, когда
// окно закрыто, тур не идёт, а настроено ещё не всё: закрыть онбординг можно
// одним кликом, но дорогу назад стоит оставить на виду.

export function OnboardingLauncher() {
  const onboarding = useOnboarding();
  if (!onboarding?.showLauncher) return null;
  return (
    <button className="ob-launcher" type="button" onClick={onboarding.open}>
      <Icon name="sparkles" size={17} strokeWidth={1.9} />
      {t("onboarding.title")}
      <small>{t("onboarding.progress_short", { done: onboarding.doneCount, total: onboarding.steps.length })}</small>
    </button>
  );
}
