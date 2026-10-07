import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { t } from "../../../i18n";
import { HttpToolForm } from "./HttpToolForm";
import { ServerConnection } from "./ServerConnection";
import { serverDraft } from "./model";
import { useServerEditor } from "./useServerEditor";
import { draftErrors } from "./validation";
import { initialValidationState, validationAfterBlur, validationAfterChange, visibleValidationErrors } from "./validationState";
import type { ServerKind } from "./types";

describe("показ ошибок настроек MCP и HTTP", () => {
  it.each(["mcp", "http"] as const)("открывает пустую форму %s без ошибок и позволяет проверить сохранение", (kind: ServerKind) => {
    function Form() {
      const editor = useServerEditor(kind, null, () => undefined);
      return kind === "mcp" ? <ServerConnection editor={editor} /> : <HttpToolForm editor={editor} />;
    }
    const markup = renderToStaticMarkup(<Form />);
    expect(markup).not.toContain('role="alert"');
    expect(markup).not.toContain("is-invalid");
    expect(markup).not.toContain('aria-invalid="true"');
    expect(markup).toMatch(new RegExp(`<button[^>]*(?<!disabled="")>${t("common.save")}</button>`));
    const saveButton = markup.match(new RegExp(`<button[^>]*>${t("common.save")}</button>`))?.[0];
    expect(saveButton).not.toContain("disabled");
  });

  it("не показывает ошибки при выходе из нетронутого поля или во время первого ввода", () => {
    const draft = serverDraft("http");
    expect(visibleValidationErrors(draftErrors(draft), validationAfterBlur(initialValidationState, "name"))).toEqual({});
    const changed = { ...draft, name: " " };
    const state = validationAfterChange(initialValidationState, draft, changed);
    expect(visibleValidationErrors(draftErrors(changed), state)).toEqual({});
    expect(Object.keys(visibleValidationErrors(draftErrors(changed), validationAfterBlur(state, "name")))).toEqual(["name"]);
  });

  it("показывает ошибку изменённого HTTP-поля после выхода и убирает её после исправления", () => {
    const draft = serverDraft("http");
    const invalid = { ...draft, externalServer: { ...draft.externalServer, toolName: "get order" } };
    const state = validationAfterBlur(validationAfterChange(initialValidationState, draft, invalid), "toolName");
    expect(Object.keys(visibleValidationErrors(draftErrors(invalid), state))).toEqual(["toolName"]);
    const corrected = { ...invalid, externalServer: { ...invalid.externalServer, toolName: "get_order" } };
    expect(visibleValidationErrors(draftErrors(corrected), state)).toEqual({});
  });

  it.each(["mcp", "http"] as const)("после попытки сохранения %s показывает все ошибки, сохраняя обязательность полей", (kind) => {
    const errors = draftErrors(serverDraft(kind));
    expect(Object.keys(errors)).toEqual(kind === "mcp" ? ["name", "url"] : ["name", "url", "toolName", "description"]);
    expect(visibleValidationErrors(errors, { ...initialValidationState, submitted: true })).toEqual(errors);
  });

  it("не раскрывает ошибку адреса при изменении другого поля", () => {
    const draft = serverDraft("http");
    const next = { ...draft, name: "Название" };
    const state = validationAfterBlur(validationAfterChange(initialValidationState, draft, next), "name");
    expect(visibleValidationErrors({ url: ["Недопустимый адрес"] }, state)).toEqual({});
  });
});
