import { Modal } from "antd";
import { t } from "../../i18n";
import { Button } from "../../shared/ui-controls";
import { validateConfiguration, type Configuration } from "./model";
import type { useSkillLeaveGuard } from "./useSkillLeaveGuard";

export function SkillLeaveDialog({
  leave,
  busy,
  conflict,
  save,
  draft,
  error,
}: {
  leave: ReturnType<typeof useSkillLeaveGuard>;
  busy: boolean;
  conflict: boolean;
  save: () => Promise<boolean>;
  draft: Configuration;
  error: string;
}) {
  return (
    <Modal
      open={!!leave.pending}
      title={t("skills.leave")}
      onCancel={leave.stay}
      footer={
        <div className="skill-actions">
          <Button variant="secondary" disabled={busy} onClick={leave.proceed}>
            {t("skills.discard")}
          </Button>
          <Button variant="secondary" disabled={busy} onClick={leave.stay}>
            {t("skills.stay")}
          </Button>
          <Button
            variant="primary"
            disabled={busy || conflict}
            onClick={async () => {
              if (await save()) leave.proceed();
              else if (Object.keys(validateConfiguration(draft)).length) leave.stay();
            }}>
            {t("common.save")}
          </Button>
        </div>
      }>
      <p>{t("skills.leave_hint")}</p>
      {error && (
        <div className="skill-notice is-error" role="alert">
          {error}
        </div>
      )}
    </Modal>
  );
}
