import type { ServiceField } from "./services/types";

/** Reuse the native adapter schema renderer instead of creating a second form kit. */
export const GREEN_API_FIELDS: ServiceField[] = [
  {
    name: "idInstance", type: "string", title: "ID инстанса", hint: "Из кабинета GREEN API",
    placeholder: "Например, 7103123456", required: true, nullable: false,
    secret: false, control: "text@1",
  },
  {
    name: "apiTokenInstance", type: "string", title: "API Token Instance",
    hint: "Токен передаётся только при сохранении и не отображается повторно",
    placeholder: "", required: true, nullable: false, secret: true, control: "secret@1",
  },
  {
    name: "apiUrl", type: "string", title: "API URL",
    hint: "HTTPS-адрес API из кабинета GREEN API",
    placeholder: "https://...green-api.com", required: true, nullable: false,
    secret: false, control: "url@1",
  },
  {
    name: "mediaUrl", type: "string", title: "Media URL",
    hint: "HTTPS-адрес медиасервера из кабинета GREEN API",
    placeholder: "https://...green-api.com", required: true, nullable: false,
    secret: false, control: "url@1",
  },
];

export type GreenApiValues = {
  idInstance: string;
  apiTokenInstance: string;
  apiUrl: string;
  mediaUrl: string;
};

export const EMPTY_GREEN_API_VALUES: GreenApiValues = {
  idInstance: "", apiTokenInstance: "", apiUrl: "", mediaUrl: "",
};

export function greenApiReady(values: GreenApiValues): boolean {
  const api = /^https:\/\/[a-z0-9.-]+\.green-api\.com\/?$/i;
  return /^\d{4,20}$/.test(values.idInstance.trim()) &&
    values.apiTokenInstance.length >= 8 && !/\s/.test(values.apiTokenInstance) &&
    api.test(values.apiUrl.trim()) && api.test(values.mediaUrl.trim());
}

export const isGreenApiService = (service: string): boolean =>
  service === "green_api_telegram" || service === "green_api_max";
