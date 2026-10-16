import { Icon } from "../../shared/icons";
import { t } from "../../i18n";
import { formatDuration } from "./VoiceMessage";
import type { useVoiceRecorder } from "./useVoiceRecorder";

/** Кадр H: идёт запись голосового — редактор заменён строкой записи. */
export function ComposerVoiceRecorder({ recorder }: { recorder: ReturnType<typeof useVoiceRecorder> }) {
  return (
    <div className="sales-composer">
      <div className="voice-recorder">
        <button aria-label={t("conversations.cancel_recording")} className="voice-recorder-cancel" title={t("conversations.cancel_recording")} type="button" onClick={recorder.cancel}>
          <Icon name="trash" size={16} />
        </button>
        <span className="voice-recorder-timer"><i />{formatDuration(recorder.seconds)}</span>
        <span className="voice-recorder-hint">
          {recorder.state === "sending" ? t("common.sending") : t("conversations.recording_esc_cancels_enter_sends")}
        </span>
        <button className="voice-recorder-send" disabled={recorder.state === "sending"} type="button" onClick={recorder.stopAndSend}>
          <Icon name="send" size={14} />{t("conversations.send")}</button>
      </div>
      {recorder.errorText && <div className="sales-composer-error">{recorder.errorText}</div>}
    </div>
  );
}
