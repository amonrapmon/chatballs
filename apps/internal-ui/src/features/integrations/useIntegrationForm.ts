import { useState } from "react";
import { api } from "../../api/client";
import { t } from "../../i18n";
import { EMAIL_CONFIG_DEFAULTS, emailConfigFromIntegration, emailConfigPayload } from "./EmailFields";
import { connectionGroupSettings, formatAllowedOrigins, gatewayConfigPayload, invalidAllowedOrigin, parseAllowedOrigins, PROVIDERS, webWidgetSnippet,
  type Integration, type IntegrationKind, type IntegrationProvider } from "./model";
import { integrationProviderOptions } from "./integrationFormModel";
import { EMPTY_GREEN_API_VALUES, greenApiReady, isGreenApiService, type GreenApiValues } from "./greenApiFields";

export function useIntegrationForm({ initial, kind, allowedProviders, onSaved }: {
  initial: Integration | null; kind: IntegrationKind; allowedProviders?: readonly IntegrationProvider[]; onSaved: () => void;
}) {
  const isEdit = initial !== null;
  const options = integrationProviderOptions(kind, allowedProviders);
  const [provider, setProvider] = useState<IntegrationProvider>(initial?.provider ?? (options[0]?.[0] as IntegrationProvider | undefined) ?? "OPENROUTER");
  const [name, setName] = useState(initial?.name ?? "");
  const [secret, setSecret] = useState("");
  const [connectorService, setConnectorService] = useState(initial?.config.connectorService ?? "");
  const [greenApiValues, setGreenApiValues] = useState<GreenApiValues>(EMPTY_GREEN_API_VALUES);
  // Keep the newly created Integration ID if provisioning fails, so Retry does
  // not create a duplicate Channel or connection.
  const [pendingConnectorId, setPendingConnectorId] = useState<number | null>(null);
  const setGreenApiField = (field: string, value: unknown) => {
    if (!(field in EMPTY_GREEN_API_VALUES)) return;
    setGreenApiValues(current => ({ ...current, [field]: String(value ?? "") }));
  };
  const [sourceId, setSourceId] = useState(initial?.config.sourceId ?? "");
  const [baseUrl, setBaseUrl] = useState(initial?.config.baseUrl ?? "");
  const [defaultModel, setDefaultModel] = useState(initial?.config.defaultModel ?? "");
  const [transcriptionModel, setTranscriptionModel] = useState(initial?.config.transcriptionModel ?? "");
  const [proxyUrl, setProxyUrl] = useState(initial?.config.proxyUrl ?? "");
  const [allowedOrigins, setAllowedOrigins] = useState(formatAllowedOrigins(initial?.config.allowedOrigins ?? []));
  const [emailConfig, setEmailConfig] = useState(initial ? emailConfigFromIntegration(initial.config) : EMAIL_CONFIG_DEFAULTS);
  const [channelId, setChannelId] = useState(initial?.channel ? String(initial.channel.id) : "");
  const [isNotifier, setIsNotifier] = useState(initial?.config.purpose === "notifications");
  const [groupId, setGroupId] = useState(initial?.channel?.groupId ? String(initial.channel.groupId) : "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const meta = PROVIDERS[provider];
  const isMessenger = meta.kind === "MESSENGER";
  const isWeb = provider === "WEB";
  const isEmail = provider === "EMAIL";
  const isDemo = provider === "DEMO";
  const isConnector = provider === "API_CONNECTOR";
  const hasNotifierPurpose = isNotifier && !isConnector;
  const isGateway = provider === "GATEWAY";
  const widgetSnippet = isWeb && initial?.webChatWidget
    ? webWidgetSnippet(initial.webChatWidget.publicKey)
    : "";

  async function copySnippet() {
    try {
      await navigator.clipboard.writeText(widgetSnippet);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  const customReady = provider !== "CUSTOM" || (baseUrl.trim().length > 0 && defaultModel.trim().length > 0);
  const emailReady = !isEmail || Boolean(emailConfig.email.trim() && emailConfig.imapHost.trim() && emailConfig.smtpHost.trim());
  // Без доменов виджет сохранится, но на сайте покажет «Чат временно недоступен»:
  // origin_allowed на пустом списке запрещает всё. Поэтому поле обязательное.
  const originList = parseAllowedOrigins(allowedOrigins);
  const badOrigin = isWeb ? invalidAllowedOrigin(originList) : undefined;
  const webReady = !isWeb || (originList.length > 0 && !badOrigin);
  const isGreenApi = isConnector && isGreenApiService(connectorService);
  const greenApiTouched = Object.values(greenApiValues).some(value => value.trim().length > 0);
  const mustProvision = isGreenApi && (!isEdit || greenApiTouched);
  const lockedPlatform = isEdit && Boolean(initial.config.callbackUrl) &&
    initial.config.connectorService !== connectorService;
  const connectorReady = !isConnector || ["green_api_max", "green_api_telegram", "green_api_whatsapp", "custom_adapter"].includes(connectorService);
  const gatewayReady = !isGateway || (sourceId.trim().length > 0 && baseUrl.trim().length > 0);
  const ready = options.some(([option]) => option === provider) && name.trim().length > 0 &&
    customReady && emailReady && webReady && connectorReady && gatewayReady && !lockedPlatform &&
    (!mustProvision || greenApiReady(greenApiValues)) &&
    (isEdit || !meta.testable || secret.trim().length > 0);

  async function submit() {
    if (!ready) return;
    setSubmitting(true);
    setError(null);
    const config = isGateway
      ? gatewayConfigPayload(sourceId, baseUrl)
      : isEmail
      ? emailConfigPayload(emailConfig)
      : isWeb
        ? {
            allowedOrigins: originList,
            title: initial?.config.title ?? "",
            accent: initial?.config.accent ?? "",
            greeting: initial?.config.greeting ?? "",
            quickReplies: initial?.config.quickReplies ?? [],
            consentText: initial?.config.consentText ?? "",
            consentVersion: initial?.config.consentVersion ?? "",
          }
        : isConnector
          ? { connectorService }
          : { baseUrl: baseUrl.trim(), defaultModel: defaultModel.trim(), transcriptionModel: transcriptionModel.trim(), proxyUrl: proxyUrl.trim(), purpose: hasNotifierPurpose ? "notifications" : "" };
    // Сервисный бот уведомлений не привязывается к каналу продаж.
    const channel = isMessenger ? {
      channelId: channelId && (isGateway || !hasNotifierPurpose) ? Number(channelId) : null,
      ...((isGateway || !hasNotifierPurpose) ? connectionGroupSettings(initial, channelId, groupId) : {}),
    } : {};
    try {
      let integrationId = initial?.id ?? pendingConnectorId;
      if (isEdit) {
        await api(`/api/v1/integrations/${initial.id}/`, {
          method: "PATCH",
          body: JSON.stringify({ name, config, ...channel, ...(secret.trim() ? { secret } : {}) }),
        });
      } else if (!integrationId) {
        const response = await api<{ integration: { id: number } }>("/api/v1/integrations/", {
          method: "POST",
          body: JSON.stringify({ provider, name, ...(isConnector ? {} : { secret }), config, ...channel }),
        });
        integrationId = response.integration.id;
        if (isGreenApi) setPendingConnectorId(integrationId);
      }
      if (mustProvision && integrationId) {
        await api(`/api/v1/integrations/${integrationId}/green-api/`, {
          method: "POST",
          body: JSON.stringify({
            idInstance: greenApiValues.idInstance.trim(),
            apiTokenInstance: greenApiValues.apiTokenInstance,
            apiUrl: greenApiValues.apiUrl.trim(),
            mediaUrl: greenApiValues.mediaUrl.trim(),
          }),
        });
      }
      onSaved();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("common.could_not_save"));
    } finally {
      setSubmitting(false);
    }
  }

  return { isEdit, options, provider, setProvider, name, setName, secret, setSecret, sourceId, setSourceId, greenApiValues, setGreenApiField, isGreenApi, lockedPlatform, pendingConnectorId, baseUrl, setBaseUrl, defaultModel, setDefaultModel, transcriptionModel, setTranscriptionModel, proxyUrl, setProxyUrl, allowedOrigins, setAllowedOrigins, emailConfig, setEmailConfig, channelId, setChannelId, groupId, setGroupId, isNotifier, setIsNotifier, submitting, error, copied, meta, isMessenger, isWeb, isEmail, isDemo, isConnector, connectorService, setConnectorService, isGateway, widgetSnippet, copySnippet, badOrigin, ready, submit };
}
