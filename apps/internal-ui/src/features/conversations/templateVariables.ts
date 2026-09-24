import type { MessageKey } from "../../i18n/ru";

// Переменные шаблонов ответов. В тексте шаблона хранится код, а не слово на
// языке интерфейса: язык организации меняется, код — нет. Тот же список
// проверяет сервер при сохранении (conversations/chat_extras_views.py).

export const TEMPLATE_VARIABLES = ["client_name", "operator_name", "company"] as const;

export type TemplateVariable = (typeof TEMPLATE_VARIABLES)[number];
export type TemplateValues = Partial<Record<TemplateVariable, string>>;

export const TEMPLATE_VARIABLE_LABEL: Record<TemplateVariable, MessageKey> = {
  client_name: "conversations.variable_client_name",
  operator_name: "conversations.variable_operator_name",
  company: "conversations.variable_company",
};

const TOKEN = /\{\{\s*(\w+)\s*\}\}/g;

export function variableToken(variable: TemplateVariable): string {
  return `{{${variable}}}`;
}

function isVariable(name: string): name is TemplateVariable {
  return (TEMPLATE_VARIABLES as readonly string[]).includes(name);
}

/** Подставляет известные значения. Переменная без значения (у гостя нет
 *  имени) остаётся в тексте как есть — её заполнит оператор. */
export function renderTemplate(text: string, values: TemplateValues): string {
  return text.replace(TOKEN, (token, name: string) => {
    const value = isVariable(name) ? values[name]?.trim() : "";
    return value || token;
  });
}

/** Переменные, которые остались в тексте незаполненными, без повторов. */
export function unfilledVariables(text: string): TemplateVariable[] {
  const found = [...text.matchAll(TOKEN)].map((match) => match[1]).filter(isVariable);
  return [...new Set(found)];
}
