import { useState } from "react";

import { t } from "./i18n";

const SITE = "https://chatballs.ru";

/** Подпись под полем ввода: чей это чат.
 *
 * Ссылка открывается новой вкладкой: виджет живёт в iframe на чужой странице,
 * и уводить эту страницу с собой он не должен. Наведение подсвечивает подпись
 * акцентом канала — состояние держится в React: вокруг только inline-стили,
 * а :hover в них не живёт.
 */
export function BrandFooter({ accent }: { accent: string }) {
  const [hover, setHover] = useState(false);
  return (
    <div style={{ flex: "none", background: "#f7f8fa", padding: "7px 14px 10px", display: "flex", justifyContent: "center" }}>
      <a
        href={SITE}
        target="_blank"
        rel="noopener noreferrer"
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        style={{
          display: "inline-flex",
          alignItems: "baseline",
          gap: 4,
          fontSize: 13,
          lineHeight: 1,
          textDecoration: "none",
          transition: "color .18s ease",
        }}
      >
        <span style={{ fontWeight: 400, color: hover ? accent : "#8c8c8c", transition: "color .18s ease" }}>{t("chat.powered_by")}</span>
        <span style={{ fontWeight: 700, color: hover ? accent : "#262626", transition: "color .18s ease" }}>Chatballs</span>
      </a>
    </div>
  );
}
