/* Ссылки на Центр помощи продукта.

   Центр помощи один на продукт и живёт на домене разработчика: это
   документация Chatballs, а не портал организации, поэтому адрес здесь
   постоянный и от установки не зависит. Порталы самой организации
   настраиваются в разделе «Порталы» и к этим ссылкам отношения не имеют. */

const HELP_CENTER_URL = "https://chatballs.com.edevs.tech";

export function helpArticleUrl(slug: string): string {
  return `${HELP_CENTER_URL}/articles/${slug}`;
}
