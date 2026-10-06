import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { fmt, t } from "../../../i18n";
import type { Integration } from "../model";
import { McpTools } from "./McpTools";
import type { ExternalServer, McpTool } from "./types";

const tool: McpTool = { name: "order_status", title: "Order status", description: "Get status",
  inputSchema: {}, readOnlyHint: false, readOnlyConfirmation: null };
const refreshedAt = "2026-10-05T09:00:00Z";

function render(state: ExternalServer["toolsState"], tools: McpTool[] = [], refreshing = false) {
  const editor = { integration: { externalServer: { type: "mcp", url: "https://example.com/mcp", tools,
    toolsState: state, toolsRefreshedAt: refreshedAt } } as Integration,
    busy: refreshing, refreshing, dirty: false, error: "", action: async () => true };
  return renderToStaticMarkup(<McpTools editor={editor} openConnection={() => undefined} />);
}

describe("MCP tool list states", () => {
  it("offers initial loading and refreshing an empty server", () => {
    const initial = render("not_loaded");
    expect(initial).toContain(t("servers.not_loaded"));
    expect(initial).toContain(t("servers.load"));
    const empty = render("no_tools");
    expect(empty).toContain(t("servers.no_tools"));
    expect(empty).toContain(t("servers.refresh_empty"));
    expect(empty).not.toContain(t("servers.not_loaded"));
  });

  it("replaces rows with progress and blocks a second refresh while refreshing", () => {
    const markup = render("loaded", [tool], true);
    expect(markup).toContain('role="status"');
    expect(markup).toContain(t("servers.refreshing"));
    expect(markup).toContain('disabled=""');
    expect(markup).not.toContain(tool.name);
  });

  it.each(["unreachable", "unauthorized", "address_forbidden"] as const)("retains the dated snapshot without confirmation actions on %s", (state) => {
    const markup = render(state, [tool]);
    expect(markup).toContain(t(`servers.${state}`));
    expect(markup).toContain('class="server-tool-row is-stale"');
    expect(markup).toContain(tool.title);
    expect(markup).toContain(fmt.shortDateTime(refreshedAt));
    expect(markup).not.toContain(t("servers.confirm_read"));
    expect(markup).not.toContain(t("servers.revoke"));
  });

  it("directs forbidden addresses to connection settings without an initial-load action", () => {
    const markup = render("address_forbidden");
    expect(markup).toContain(t("servers.change_address"));
    expect(markup).toContain(t("servers.forbidden_empty"));
    expect(markup).toContain(t("servers.forbidden_empty_hint"));
    expect(markup).not.toContain(t("servers.load"));
    expect(markup).not.toContain(t("servers.not_loaded_hint"));
  });

  it("counts server hints and administrator confirmations as read only", () => {
    const confirmation = { confirmedBy: { id: 2, name: "Elena" }, confirmedAt: refreshedAt };
    const markup = render("loaded", [tool, { ...tool, name: "prices", readOnlyHint: true },
      { ...tool, name: "promotions", readOnlyConfirmation: confirmation }]);
    expect(markup).toContain(t("servers.refreshed", { time: fmt.shortDateTime(refreshedAt) }));
    expect(markup.match(/server-read-badge is-read/g)).toHaveLength(2);
    expect(markup.match(/class="link"/g)).toHaveLength(1);
    expect(markup).toContain(t("servers.confirmed", { name: "Elena", time: fmt.shortDate(refreshedAt) }));
    expect(markup).toMatch(/<button class="[^"]*row-menu-button[^"]*"/);
  });
});
