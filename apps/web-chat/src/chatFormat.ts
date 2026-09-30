import { fmt, t } from "./i18n";
export function formatTime(iso: string | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : fmt.time(date);
}

export function formatBytes(bytes: number): string {
  // Байты — только у совсем маленьких файлов: «1 КБ» ниже килобайта врало бы.
  if (bytes < 1024) return t("unit.b", { value: bytes });
  const { value, unit } = fmt.bytes(bytes);
  return t(unit === "mb" ? "unit.mb" : "unit.kb", { value });
}

