export type CrmProvider = "NONE" | "DIKIDI" | "YCLIENTS";

export type CrmCompany = {
  id: number;
  name: string;
  externalCompanyId: string;
  isPrimary: boolean;
  isActive: boolean;
};
export type CrmBinding = { integrationId: number; companyId: number };
export type CrmConfiguration = {
  provider: CrmProvider;
  companies: CrmCompany[];
  bindings: CrmBinding[];
};
export type CrmLink = {
  companyId: number;
  companyName: string;
  provider: Exclude<CrmProvider, "NONE">;
  url: string;
};
export type CrmLinkState =
  | "ok" | "multiple_companies" | "partial" | "ambiguous_company"
  | "no_company" | "inactive_company" | "no_phone" | "disabled";
export type CrmLinks = { state: CrmLinkState; links: CrmLink[] };

export function isTrustedCrmUrl(url: string, provider: CrmLink["provider"]): boolean {
  try {
    const target = new URL(url);
    return target.protocol === "https:" && target.username === "" && target.password === "" && target.port === ""
      && ((provider === "DIKIDI" && target.hostname === "dikidi.net"
        && target.pathname === "/ru/owner/clients/")
        || (provider === "YCLIENTS" && target.hostname === "yclients.ru"
        && /^\/clients\/[0-9]+\/base$/.test(target.pathname)));
  } catch {
    return false;
  }
}
