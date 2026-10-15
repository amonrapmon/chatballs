import { api } from "../api/client";
import type { CrmCompany, CrmConfiguration, CrmLinks, CrmProvider } from "./model";

const BASE = "/api/v1/company/crm/";

export const loadCrm = () => api<CrmConfiguration>(BASE);
export const saveCrmProvider = (provider: CrmProvider) =>
  api<{ provider: CrmProvider }>(BASE + "provider/", {
    method: "PATCH", body: JSON.stringify({ provider }),
  });
export const createCrmCompany = (name: string, externalCompanyId: string) =>
  api<{ company: CrmCompany }>(BASE + "companies/", {
    method: "POST", body: JSON.stringify({ name, externalCompanyId }),
  });
export const updateCrmCompany = (id: number, changes: Partial<{
  name: string; externalCompanyId: string; isPrimary: boolean; isActive: boolean;
}>) => api<{ company: CrmCompany }>(BASE + "companies/" + id + "/", {
  method: "PATCH", body: JSON.stringify(changes),
});
export const removeCrmCompany = (id: number) =>
  api<void>(BASE + "companies/" + id + "/", { method: "DELETE" });
export const assignCrmCompany = (integrationId: number, companyId: number) =>
  api<{ integrationId: number; companyId: number }>(BASE + "bindings/" + integrationId + "/", {
    method: "PUT", body: JSON.stringify({ companyId }),
  });
export const unassignCrmCompany = (integrationId: number) =>
  api<void>(BASE + "bindings/" + integrationId + "/", { method: "DELETE" });

export const loadConversationCrmLinks = (id: number) =>
  api<CrmLinks>(BASE + "links/conversations/" + id + "/");
export const loadContactCrmLinks = (id: number) =>
  api<CrmLinks>(BASE + "links/contacts/" + id + "/");
