import type { ReportDirectory, ReportFilters } from "./types";

type Connection = ReportDirectory["connections"][number];

/** UI grouping only. Never substitute this for Integration.provider in event storage. */
export function reportingPlatform(connection: Connection): string {
  return connection.displayProvider || connection.provider;
}

export function connectionsForPlatform(directory: ReportDirectory, platform: string): Connection[] {
  return directory.connections.filter((connection) => !platform || reportingPlatform(connection) === platform);
}

/** The core API accepts one connection ID, not a set. Do not show an inaccurate platform total. */
export function requiresSpecificConnection(filters: ReportFilters, directory: ReportDirectory): boolean {
  if (!filters.platform || filters.connection) return false;
  const candidates = connectionsForPlatform(directory, filters.platform);
  return candidates.length === 0 || candidates.some((connection) => connection.provider !== filters.platform);
}

export function chooseReportingPlatform(filters: ReportFilters, directory: ReportDirectory, platform: string): ReportFilters {
  if (!platform) return { ...filters, platform: "", transport: "", connection: "" };
  const candidates = connectionsForPlatform(directory, platform);
  const hasConnector = candidates.some((connection) => connection.provider !== platform);
  if (!hasConnector && candidates.length) return { ...filters, platform, transport: platform, connection: "" };
  if (candidates.length === 1) return {
    ...filters, platform, transport: candidates[0].provider, connection: String(candidates[0].id),
  };
  return { ...filters, platform, transport: "", connection: "" };
}

export function chooseReportingConnection(filters: ReportFilters, directory: ReportDirectory, id: string): ReportFilters {
  const connection = directory.connections.find((item) => String(item.id) === id);
  if (!id || !connection) {
    const platform = filters.platform || "";
    const hasConnector = connectionsForPlatform(directory, platform).some((item) => item.provider !== platform);
    return { ...filters, connection: "", transport: platform && !hasConnector ? platform : "" };
  }
  if (filters.platform && reportingPlatform(connection) !== filters.platform) {
    return { ...filters, connection: "", transport: "" };
  }
  return { ...filters, connection: id, transport: filters.platform ? connection.provider : "" };
}
