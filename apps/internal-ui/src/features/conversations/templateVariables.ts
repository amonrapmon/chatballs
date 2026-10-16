// Переменные шаблонов ответов. Значения подставляет сервер — для видимого
// сотруднику диалога; на клиенте остаётся только проверка, что в отправляемом
// тексте не осталось маркеров известных переменных. Разбор совпадает с
// серверным (conversations/template_variables.py).

export const TEMPLATE_TOKEN = /\{\{([^{}]*?)\}\}/g;

const LEGACY_VARIABLES = ["client_name", "operator_name", "company"];
const CONTACT_FIELD = /^contact\.(email|phone|company|city|description)$/;
// Пространство дополнительных полей остаётся занятым и после удаления поля.
const CUSTOM_FIELD = /^contact\.fields\.[1-9][0-9]*\.[a-z][a-z0-9_]{0,39}$/;

/** Переменные, которые остались в тексте незаполненными, без повторов.
 *  `additionalKeys` — ключи, о которых сообщил сервер при подстановке или
 *  отправке: они учитываются, пока их маркер есть в тексте. */
export function unfilledVariables(text: string, additionalKeys: string[] = []): string[] {
  const found = [...text.matchAll(TEMPLATE_TOKEN)]
    .map((match) => match[1].trim())
    .filter((name) => LEGACY_VARIABLES.includes(name) || CONTACT_FIELD.test(name) || CUSTOM_FIELD.test(name) || additionalKeys.includes(name));
  return [...new Set(found)];
}
