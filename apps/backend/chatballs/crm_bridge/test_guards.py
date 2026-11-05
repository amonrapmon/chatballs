"""Database and RLS guards must withstand ORM bulk bypasses."""

from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase

from chatballs.crm_bridge.models import CRMCompany, CRMConnectionBinding, CRMOrganizationConfig
from chatballs.identity.models import Organization
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.tenancy.database import set_local_tenant


class CRMBridgeGuardTests(TransactionTestCase):
    def setUp(self):
        self.first = Organization.objects.create(name="First", slug="crm-guard-first")
        self.second = Organization.objects.create(name="Second", slug="crm-guard-second")
        for org in (self.first, self.second):
            CRMOrganizationConfig.objects.create(organization=org, provider="DIKIDI", last_active_provider="DIKIDI")
        self.company = CRMCompany.objects.create(
            organization=self.first, name="A", external_company_id="123", is_primary=True,
        )
        self.foreign_company = CRMCompany.objects.create(
            organization=self.second, name="B", external_company_id="456", is_primary=True,
        )
        self.integration = Integration.objects.create(
            organization=self.first, name="TG",
            kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.TELEGRAM,
        )

    def test_cross_tenant_binding_rejected_at_database_level(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            CRMConnectionBinding.objects.bulk_create([
                CRMConnectionBinding(
                    organization=self.first, integration=self.integration,
                    crm_company=self.foreign_company,
                )
            ])
        binding = CRMConnectionBinding.objects.create(
            organization=self.first, integration=self.integration, crm_company=self.company,
        )
        with self.assertRaises(DatabaseError), transaction.atomic():
            CRMConnectionBinding.objects.filter(pk=binding.pk).update(
                crm_company=self.foreign_company
            )

    def test_rls_and_runtime_grants(self):
        tables = [
            "crm_bridge_crmorganizationconfig",
            "crm_bridge_crmcompany",
            "crm_bridge_crmconnectionbinding",
        ]
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relname, relrowsecurity, relforcerowsecurity, "
                "pg_get_userbyid(relowner) FROM pg_class WHERE relname = ANY(%s)",
                [tables],
            )
            rows = cursor.fetchall()
        self.assertEqual(len(rows), len(tables))
        self.assertTrue(all(on and forced and owner == "chatballs_schema" for _, on, forced, owner in rows))
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            self.assertEqual(CRMCompany.objects.count(), 0)
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            set_local_tenant(self.first.pk)
            self.assertEqual(CRMCompany.objects.count(), 1)
            self.assertEqual(CRMCompany.objects.filter(pk=self.foreign_company.pk).count(), 0)
            self.assertEqual(
                CRMCompany.objects.filter(pk=self.foreign_company.pk).update(name="unsafe"), 0,
            )
