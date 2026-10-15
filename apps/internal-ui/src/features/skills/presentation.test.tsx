import { renderToStaticMarkup } from "react-dom/server";
import { createI18n } from "@chatballs/shared";
import { describe, expect, it } from "vitest";
import { SkillsModelWarning } from "./SkillsModelWarning";
import { skillsRu } from "../../i18n/skills.ru";
import { skillsEn } from "../../i18n/skills.en";
import { t } from "../../i18n";

describe("skill support and affected-agent messages", () => {
  it("distinguishes unknown support from an unsupported model and hides the warning for supported models", () => {
    expect(renderToStaticMarkup(<SkillsModelWarning support={true} />)).toBe("");
    expect(renderToStaticMarkup(<SkillsModelWarning support={false} />)).toContain(t("skills.unsupported"));
    const unknown = renderToStaticMarkup(<SkillsModelWarning support={null} />);
    expect(unknown).toContain(t("skills.unknown"));
    expect(unknown).not.toContain(t("skills.unsupported"));
  });
  it("uses the correct RU/EN forms for affected agents and multiple selections", () => {
    const messages = createI18n<keyof typeof skillsRu>({ catalogs: { ru: skillsRu, en: skillsEn }, source: "ru" });
    messages.setLanguage("ru");
    expect(messages.tn("skills.save_for", 1)).toBe("Сохранить для 1 агента");
    expect(messages.tn("skills.save_for", 12)).toBe("Сохранить для 12 агентов");
    expect(messages.tn("skills.connect_count", 2)).toBe("Подключить 2 навыка");
    messages.setLanguage("en");
    expect(messages.tn("skills.save_for", 1)).toBe("Save for 1 agent");
    expect(messages.tn("skills.save_for", 2)).toBe("Save for 2 agents");
    expect(messages.tn("skills.connect_count", 0)).toBe("Connect 0 skills");
  });
});
