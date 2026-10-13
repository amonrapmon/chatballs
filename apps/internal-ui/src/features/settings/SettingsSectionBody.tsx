import { ParticipantLimitCard } from "./ParticipantLimitCard";
import { TransferSettings } from "./transfer/TransferSettings";
import type { ReactNode } from "react";
import type { EmployeeGroup, SessionUser } from "../../types";
import { OrganizationSettingsForm } from "../administration/OrganizationSettingsForm";
import { canManageSettings } from "../administration/model";
import { useAdministration } from "../administration/useAdministration";
import { IntegrationsSection } from "../integrations/IntegrationsSection";
import type { Integration } from "../integrations/model";
import { EmptyState, LoadingState } from "../../shared/ui";
import { DemoDataCard } from "./DemoDataCard";
import { CommunicationSettingsCard } from "./CommunicationSettingsCard";
import { PlatformSettingsCard } from "./PlatformSettingsCard";
import { StorageSettingsCard } from "./StorageSettingsCard";
import { GroupsSettingsCard } from "./GroupsSettingsCard";
import { QueuePolicyCard } from "./QueuePolicyCard";
import { ReplyTemplateLibrary } from "../reply-templates/ReplyTemplateLibrary";
import type { SettingsSectionKey } from "./sections";
import type { useIntegrations } from "./useIntegrations";
import { t } from "../../i18n";

export function SettingsSectionBody({ section, user, onUserUpdated, reload, groups, integrations, providers, onEditIntegration, onTemplatesChanged }: {
  section: SettingsSectionKey; user: SessionUser; onUserUpdated: (user: SessionUser) => void; reload: () => void;
  groups: EmployeeGroup[]; integrations: ReturnType<typeof useIntegrations>; providers: Integration[];
  onEditIntegration: (integration: Integration) => void;
  onTemplatesChanged: () => void;
}): ReactNode {
  if (section === "organization") return <OrganizationSection user={user} onUserUpdated={onUserUpdated} />;
  if (section === "groups") return <GroupsSettingsCard groups={groups} reload={reload} />;
  if (section === "transfer") return <><TransferSettings /><ParticipantLimitCard canManage={canManageSettings(user)} /></>;
  if (section === "queue") return <QueuePolicyCard canManage={canManageSettings(user)} />;
  if (section === "communication") return <CommunicationSettingsCard canManage={canManageSettings(user)} canManageRelay={user.isInstanceAdmin} />;
  if (section === "platform") return <PlatformSettingsCard canManage={user.isInstanceAdmin} organizationName={user.organizationName} />;
  if (section === "storage") return <StorageSettingsCard canManage={user.isInstanceAdmin} />;
  if (section === "demo") return <DemoDataCard reload={reload} />;
  if (section === "templates") return <ReplyTemplateLibrary onChanged={onTemplatesChanged} />;
  if (integrations.loading) return <LoadingState />;
  if (integrations.failed) return <EmptyState title={t("settings.could_not_load_integrations")} />;
  return <IntegrationsSection kind={section === "ai" ? "LLM_PROVIDER" : "MESSENGER"}
    items={section === "ai" ? providers : integrations.items.filter(item => item.kind !== "LLM_PROVIDER")}
    reload={integrations.reload} onEdit={onEditIntegration} />;
}

function OrganizationSection({ user, onUserUpdated }: { user: SessionUser; onUserUpdated: (user: SessionUser) => void }) {
  const page = useAdministration({ section: "organization", user, onUserUpdated });
  if (page.loading) return <LoadingState />;
  if (!page.organization) return <EmptyState title={page.error || t("settings.could_not_load_settings")} />;
  return <OrganizationSettingsForm organization={page.organization} canManage={canManageSettings(user)} saving={page.saving}
    message={page.message} error={page.error} timezones={page.timezones} languages={page.languages} onChange={page.setOrganization}
    onSave={() => void page.save()} onUploadLogo={file => void page.uploadLogo(file)} onRemoveLogo={() => void page.removeLogo()} />;
}
