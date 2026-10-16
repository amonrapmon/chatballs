"""Data confined to Django's disposable test database."""

from uuid import uuid4

from django.test import TransactionTestCase

from chatballs.identity.models import EmployeeRole, HumanUser, Organization, OrganizationMembership
from chatballs.identity.work_status_codes import WorkStatus
from chatballs.identity.work_status_services import change_work_status
from chatballs.tenancy.context import TenantContext


class WorkStatusTestBase(TransactionTestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Status", slug="status")
        self.foreign = Organization.objects.create(name="Foreign", slug="foreign-status")
        self.user = HumanUser.objects.create(email="status@example.test")
        self.membership = OrganizationMembership.objects.create(
            organization=self.organization, user=self.user, role=EmployeeRole.EMPLOYEE,
        )
        self.other = OrganizationMembership.objects.create(
            organization=self.foreign, user=self.user, role=EmployeeRole.EMPLOYEE,
        )
        self.context = TenantContext.for_membership(self.membership)

    def change(self, status=WorkStatus.READY, version=0, key=None, context=None):
        return change_work_status(
            context=context or self.context, status=status,
            expected_version=version, operation_id=key or uuid4(),
        )
