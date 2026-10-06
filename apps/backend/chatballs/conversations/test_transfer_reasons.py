from chatballs.conversations.transfer_models import TransferReason
from chatballs.conversations.transfer_services import save_reason
from chatballs.conversations.transfer_test_base import TransferTestBase
from chatballs.identity.models import EmployeeRole
from chatballs.tenancy.context import TenantContext


class TransferReasonTests(TransferTestBase):
    def test_catalogue_uses_server_pagination(self):
        TransferReason.objects.create(organization=self.organization, code="another", name="Another")
        result = self.client.get(self.url, {"pageSize": 1, "page": 2})
        self.assertEqual(result.status_code, 200)
        self.assertEqual((result.data["page"], result.data["pageSize"], result.data["total"]), (2, 1, 2))
        self.assertEqual([row["id"] for row in result.data["items"]], [self.reason.pk])

    def test_owner_and_admin_crud_soft_disables(self):
        for role in (EmployeeRole.OWNER, EmployeeRole.ADMIN):
            with self.subTest(role=role):
                self.client.force_authenticate(self.members[role].user)
                result = self.client.post(self.url, {
                    "code": role.lower(), "name": "New reason", "organizationId": self.foreign.pk
                }, format="json")
                self.assertEqual(result.status_code, 201, result.data)
                reason_id = result.data["reason"]["id"]
                detail = f"{self.url}{reason_id}/"
                self.assertEqual(self.client.get(detail).status_code, 200)
                updated = self.client.patch(detail, {"code": f"{role.lower()}-updated", "name": "Updated"}, format="json")
                self.assertEqual(updated.status_code, 200)
                self.assertEqual(updated.data["reason"]["name"], "Updated")
                self.assertEqual(self.client.delete(detail).status_code, 204)
                reason = TransferReason.objects.get(pk=reason_id)
                self.assertEqual(reason.organization_id, self.organization.pk)
                self.assertFalse(reason.is_active)
                listed = self.client.get(self.url)
                self.assertEqual(listed.status_code, 200)
                self.assertNotIn(self.foreign_reason.pk, [row["id"] for row in listed.data["items"]])

    def test_employee_cannot_access_any_crud_method_or_service(self):
        from rest_framework.exceptions import PermissionDenied

        employee = self.members[EmployeeRole.EMPLOYEE]
        self.client.force_authenticate(employee.user)
        for method, url, data in (
            ("get", self.url, None), ("get", f"{self.url}{self.reason.pk}/", None),
            ("post", self.url, {"code": "denied", "name": "Denied"}),
            ("patch", f"{self.url}{self.reason.pk}/", {"name": "Denied"}),
            ("delete", f"{self.url}{self.reason.pk}/", None),
        ):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(url, data=data, format="json").status_code, 403)
        with self.assertRaises(PermissionDenied):
            save_reason(context=TenantContext.for_membership(employee), data={"code": "denied", "name": "Denied"})

    def test_foreign_ids_are_not_found_and_foreign_route_is_forbidden(self):
        for method in ("get", "patch", "delete"):
            result = getattr(self.client, method)(f"{self.url}{self.foreign_reason.pk}/", data={"name": "Changed"}, format="json")
            self.assertEqual(result.status_code, 404)
        foreign_url = self.url.replace(str(self.organization.public_id), str(self.foreign.public_id))
        self.assertIn(self.client.get(foreign_url).status_code, (403, 404))
        self.foreign_reason.refresh_from_db()
        self.assertEqual(self.foreign_reason.name, "Foreign reason")
        self.assertTrue(self.foreign_reason.is_active)

    def test_validation_and_code_uniqueness_within_organization(self):
        for data in ({"code": "specialist", "name": "Duplicate"},
                     {"code": "spaces forbidden", "name": "Reason"},
                     {"code": "valid", "name": " "},
                     {"code": "x" * 65, "name": "Reason"},
                     {"code": "valid", "name": "x" * 121}):
            self.assertEqual(self.client.post(self.url, data, format="json").status_code, 400)
        # Same code was already accepted in the other organization.
        self.assertEqual(self.reason.code, self.foreign_reason.code)
        self.assertEqual(self.client.post(self.url, {"code": "another", "name": "Another"}, format="json").status_code, 201)
        other = TransferReason.objects.get(organization=self.organization, code="another")
        self.assertEqual(self.client.patch(f"{self.url}{other.pk}/", {"code": "specialist"}, format="json").status_code, 400)
