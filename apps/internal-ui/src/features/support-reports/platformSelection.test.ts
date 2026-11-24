import { describe, expect, it } from "vitest";
import { initialFilters, reportPeriod } from "./period";
import {
  chooseReportingConnection, chooseReportingPlatform, connectionsForPlatform,
  reportingPlatform, requiresSpecificConnection,
} from "./platformSelection";
import type { ReportDirectory } from "./types";

const directory = {
  connections: [
    { id: 1, name: "Native Telegram", provider: "TELEGRAM", displayProvider: "TELEGRAM" },
    { id: 4, name: "Green API Telegram", provider: "API_CONNECTOR", displayProvider: "TELEGRAM" },
    { id: 5, name: "Green API MAX", provider: "API_CONNECTOR", displayProvider: "MAX" },
    { id: 6, name: "Other Connector", provider: "API_CONNECTOR", displayProvider: "API_CONNECTOR" },
    { id: 7, name: "Native VK", provider: "VK", displayProvider: "VK" },
  ],
} as ReportDirectory;
const filters = initialFilters("Europe/Moscow");

describe("connector report platform selection", () => {
  it("resolves the display platform without changing transport", () => {
    expect(reportingPlatform(directory.connections[1])).toBe("TELEGRAM");
    expect(connectionsForPlatform(directory, "MAX").map((c) => c.id)).toEqual([5]);
    expect(reportingPlatform({ id: 8, name: "Legacy", provider: "API_CONNECTOR" })).toBe("API_CONNECTOR");
  });
  it("uses the native API transport for a single connector", () => {
    const selected = chooseReportingPlatform(filters, directory, "MAX");
    expect(selected.connection).toBe("5");
    expect(selected.transport).toBe("API_CONNECTOR");
    expect(requiresSpecificConnection(selected, directory)).toBe(false);
    expect(reportPeriod(selected).transport).toBe("API_CONNECTOR");
    expect(reportPeriod(selected).connection).toBe(5);
  });
  it("never pretends to aggregate native and connector Telegram reports", () => {
    const selected = chooseReportingPlatform(filters, directory, "TELEGRAM");
    expect(selected.connection).toBe("");
    expect(selected.transport).toBe("");
    expect(requiresSpecificConnection(selected, directory)).toBe(true);
    const single = chooseReportingConnection(selected, directory, "4");
    expect(single.transport).toBe("API_CONNECTOR");
    expect(single.connection).toBe("4");
    expect(requiresSpecificConnection(single, directory)).toBe(false);
    expect(chooseReportingConnection(single, directory, "").transport).toBe("");
  });
  it("does not count Telegram/MAX connections in generic API Connector aggregation", () => {
    const multipleGenericConnections = {
      ...directory,
      connections: [
        ...directory.connections,
        { id: 8, name: "Legacy Connector", provider: "API_CONNECTOR" },
      ],
    };
    expect(connectionsForPlatform(multipleGenericConnections, "API_CONNECTOR").map((c) => c.id)).toEqual([6, 8]);
    const selected = chooseReportingPlatform(filters, multipleGenericConnections, "API_CONNECTOR");
    expect(selected.transport).toBe("");
    expect(requiresSpecificConnection(selected, multipleGenericConnections)).toBe(true);
    const specific = chooseReportingConnection(selected, multipleGenericConnections, "6");
    expect(specific.transport).toBe("API_CONNECTOR");
    expect(specific.connection).toBe("6");
    expect(chooseReportingConnection(specific, multipleGenericConnections, "").transport).toBe("");
  });
  it("automatically selects the sole generic API Connector without including branded connections", () => {
    const selected = chooseReportingPlatform(filters, directory, "API_CONNECTOR");
    expect(reportPeriod(selected).transport).toBe("API_CONNECTOR");
    expect(reportPeriod(selected).connection).toBe(6);
    expect(requiresSpecificConnection(selected, directory)).toBe(false);
  });
  it("keeps native aggregate filtering when only native connections exist", () => {
    const selected = chooseReportingPlatform(filters, directory, "VK");
    expect(selected.connection).toBe("");
    expect(selected.transport).toBe("VK");
    expect(requiresSpecificConnection(selected, directory)).toBe(false);
  });
  it("preserves the all-connections case and rejects mismatched selections", () => {
    expect(chooseReportingPlatform(filters, directory, "").transport).toBe("");
    const telegram = chooseReportingPlatform(filters, directory, "TELEGRAM");
    expect(chooseReportingConnection(telegram, directory, "5").connection).toBe("");
  });
});
