import { useState } from "react";

import { t } from "../../i18n";
import { instanceError, patchInstance, type InstancePayload } from "./instance";

export function LanguageCard({ canManage, current, onSaved }: {
  canManage: boolean;
  current: InstancePayload;
  onSaved: (payload: InstancePayload) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [errorText, setErrorText] = useState("");

  async function save(language: string) {
    if (language === current.defaultLanguage) return;
    setBusy(true);
    setErrorText("");
    try {
      // Адрес уходит вместе с языком: PATCH проверяет его в любом случае, и
      // без него сохранение языка упало бы на «Укажите адрес установки».
      onSaved(await patchInstance({
        publicHost: current.publicHost,
        publicScheme: current.publicScheme,
        defaultLanguage: language,
      }));
    } catch (error) {
      setErrorText(instanceError(error).detail);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="administration-card">
      <div className="settings-card-head">
        <div>
          <strong>{t("settings.language_instance")}</strong>
          <small>{t("settings.language_instance_hint")}</small>
        </div>
        <div className="appearance-theme-options">
          {current.languages.map((item) => (
            <button
              className={current.defaultLanguage === item.code ? "active" : ""}
              disabled={!canManage || busy}
              key={item.code}
              lang={item.code}
              type="button"
              onClick={() => void save(item.code)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
      {errorText && <div className="administration-message error" role="alert">{errorText}</div>}
    </div>
  );
}
