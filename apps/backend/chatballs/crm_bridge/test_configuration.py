"""Focused CRM Bridge settings API and state transition checks."""

from django.test import TestCase

from chatballs.crm_bridge.models import (
    CRMCompany, CRMConnectionBinding, CRMOrganizationConfig, CRMProvider,
)
from chatballs.identity.models import (
    AuditEvent, EmployeeRole, HumanUser, Organization, OrganizationMembership,
)
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.testing import TenantAPIClient


class CRMBridgeAPITests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Studio", slug="crm-studio")
        self.foreign = Organization.objects.create(name="Elsewhere", slug="crm-foreign")
        self.owner = HumanUser.objects.create_user(email="crm-owner@example.test")
        self.employee = HumanUser.objects.create_user(email="crm-worker@example.test")
        OrganizationMembership.objects.create(
            organization=self.org, user=self.owner,
            role=EmployeeRole.OWNER, position_title="Owner",
        )
        OrganizationMembership.objects.create(
            organization=self.org, user=self.employee,
            role=EmployeeRole.EMPLOYEE, position_title="Operator",
        )
        self.client = TenantAPIClient()
        self.client.force_authenticate(user=self.owner)
        self.client.set_tenant(self.org)
        self.root = "/api/v1/company/crm/"
        self.integration = Integration.objects.create(
            organization=self.org, name="Telegram A",
            kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.TELEGRAM,
        )
        self.foreign_integration = Integration.objects.create(
            organization=self.foreign, name="Other TG",
            kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.TELEGRAM,
        )

    def set_provider(self, provider):
        return self.client.patch(self.root + "provider/", {"provider": provider}, format="json")

    def company(self, name="Main", external_company_id="515337", **kwargs):
        return self.client.post(
            self.root + "companies/",
            {"name": name, "externalCompanyId": external_company_id, **kwargs},
            format="json",
        )

    def test_provider_pause_resume_and_no_reinterpretation(self):
        response = self.client.get(self.root)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["provider"], CRMProvider.NONE)
        self.assertEqual(self.set_provider("DIKIDI").status_code, 200)
        self.assertEqual(self.company().status_code, 201)
        self.assertEqual(self.set_provider("NONE").status_code, 200)
        row = CRMOrganizationConfig.objects.get(organization=self.org)
        self.assertEqual(row.last_active_provider, CRMProvider.DIKIDI)
        self.assertEqual(self.set_provider("YCLIENTS").status_code, 409)
        self.assertEqual(self.client.get(self.root).data["provider"], "NONE")
        self.assertEqual(self.set_provider("DIKIDI").status_code, 200)
        self.assertEqual(self.client.get(self.root).data["provider"], "DIKIDI")

    def test_duplicate_external_company_and_id_validation(self):
        self.assertEqual(self.set_provider("YCLIENTS").status_code, 200)
        self.assertEqual(self.company().status_code, 201)
        self.assertIn(self.company().status_code, (400, 409))
        self.assertEqual(self.company(external_company_id="http://unsafe").status_code, 400)
        self.assertEqual(self.company(external_company_id="123abc").status_code, 400)
        self.assertEqual(CRMCompany.objects.filter(organization=self.org).count(), 1)

    def test_primary_transfer_requires_explicit_reassignment(self):
        self.assertEqual(self.set_provider("DIKIDI").status_code, 200)
        first = self.company().data["company"]["id"]
        second = self.company("Second", "987654").data["company"]["id"]
        self.assertEqual(
            self.client.delete(self.root + f"companies/{first}/").status_code, 409,
        )
        response = self.client.patch(
            self.root + f"companies/{second}/", {"isPrimary": True}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CRMCompany.objects.get(pk=first).is_primary)
        self.assertTrue(CRMCompany.objects.get(pk=second).is_primary)
        self.assertEqual(self.client.delete(self.root + f"companies/{first}/").status_code, 204)

    def test_binding_validates_tenant_and_integration_kind(self):
        self.set_provider("DIKIDI")
        company_id = self.company().data["company"]["id"]
        path = self.root + f"bindings/{self.integration.id}/"
        foreign_path = self.root + f"bindings/{self.foreign_integration.id}/"
        self.assertEqual(
            self.client.put(foreign_path, {"companyId": company_id}, format="json").status_code,
            404,
        )
        alien = CRMCompany.objects.create(
            organization=self.foreign, name="Alien",
            external_company_id="987", is_primary=True,
        )
        self.assertEqual(self.client.put(path, {"companyId": alien.pk}, format="json").status_code, 404)
        self.assertEqual(self.client.put(path, {"companyId": company_id}, format="json").status_code, 200)
        self.assertEqual(self.client.put(path, {"companyId": company_id}, format="json").status_code, 200)
        self.assertEqual(CRMConnectionBinding.objects.filter(integration=self.integration).count(), 1)
        self.assertEqual(self.client.delete(self.root + f"companies/{company_id}/").status_code, 409)
        self.assertEqual(self.client.delete(path).status_code, 204)
        self.assertEqual(self.client.delete(path).status_code, 204)

    def test_employee_cannot_modify_settings_or_read_configuration(self):
        self.client.force_authenticate(user=self.employee)
        self.assertEqual(self.client.get(self.root).status_code, 403)
        self.assertEqual(self.set_provider("YCLIENTS").status_code, 403)
        self.assertEqual(self.company().status_code, 403)
        self.assertEqual(self.client.put(
            self.root + f"bindings/{self.integration.id}/",
            {"companyId": 1}, format="json",
        ).status_code, 403)
        self.assertFalse(CRMOrganizationConfig.objects.filter(organization=self.org).exists())

    def test_disabled_crm_blocks_new_bindings_but_keeps_existing(self):
        self.set_provider("YCLIENTS")
        company_id = self.company().data["company"]["id"]
        path = self.root + f"bindings/{self.integration.id}/"
        self.assertEqual(self.client.put(path, {"companyId": company_id}, format="json").status_code, 200)
        self.assertEqual(self.set_provider("NONE").status_code, 200)
        self.assertEqual(self.client.put(path, {"companyId": company_id}, format="json").status_code, 409)
        self.assertEqual(CRMConnectionBinding.objects.filter(integration=self.integration).count(), 1)
        self.assertEqual(self.set_provider("YCLIENTS").status_code, 200)

    def test_only_mutations_get_audit_events(self):
        self.set_provider("DIKIDI")
        company_id = self.company().data["company"]["id"]
        self.assertEqual(self.set_provider("DIKIDI").status_code, 200)
        self.assertEqual(AuditEvent.objects.filter(
            organization=self.org, action="administration.crm_provider_updated"
        ).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(
            organization=self.org, action="administration.crm_company_created"
        ).count(), 1)
        path = self.root + f"bindings/{self.integration.id}/"
        self.client.put(path, {"companyId": company_id}, format="json")
        self.client.put(path, {"companyId": company_id}, format="json")
        self.assertEqual(AuditEvent.objects.filter(
            organization=self.org, action="administration.crm_binding_updated"
        ).count(), 1)

    def test_provider_switch_after_deleting_company(self):
        self.set_provider("DIKIDI")
        id_ = self.company().data["company"]["id"]
        self.assertEqual(self.client.delete(self.root + f"companies/{id_}/").status_code, 204)
        self.assertEqual(self.set_provider("YCLIENTS").status_code, 200)
        self.assertEqual(
            CRMOrganizationConfig.objects.get(organization=self.org).last_active_provider,
            "YCLIENTS",
        )

    def test_removing_integration_cleans_up_crm_binding(self):
        self.set_provider("DIKIDI")
        company_id = self.company().data["company"]["id"]
        path = self.root + f"bindings/{self.integration.id}/"
        self.assertEqual(
            self.client.put(path, {"companyId": company_id}, format="json").status_code, 200,
        )
        self.integration.delete()
        self.assertFalse(CRMConnectionBinding.objects.filter(
            organization=self.org, integration_id=self.integration.pk
        ).exists())
        self.assertTrue(CRMCompany.objects.filter(pk=company_id).exists())
