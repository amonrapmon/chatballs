import { Icon } from "../../shared/icons";
import { t } from "../../i18n";
import { formatSize } from "../ai/knowledge/model";

/** Вложение ответа клиенту: чип над полем ввода. */
export function ComposerAttachment({ file, disabled, onRemove }: { file: File; disabled: boolean; onRemove: () => void }) {
  return (
    <div className="composer-attachment">
      <Icon name="paperclip" size={14} />
      <strong title={file.name}>{file.name}</strong>
      <small>{formatSize(file.size)}</small>
      <button aria-label={t("common.remove_file")} title={t("common.remove_file")} type="button" disabled={disabled} onClick={onRemove}>
        <Icon name="xCircle" size={15} />
      </button>
    </div>
  );
}
