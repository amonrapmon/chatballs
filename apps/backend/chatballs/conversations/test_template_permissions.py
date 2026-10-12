from chatballs.conversations.template_test_base import TemplateTestBase
from chatballs.identity.models import AuditEvent
from chatballs.identity.policy import get_effective_access


class TemplatePermissionTests(TemplateTestBase):
    def test_chat_members_read_shared_objects_but_cannot_mutate_them(self):
        for resource in ("", "categories/", "tags/"):
            response = self.create(self.owner_client, resource, "SHARED")
            payload = response.json()["item" if resource else "template"]
            url = self.base + resource + f"{payload['id']}/"
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(self.create(resource=resource, scope="SHARED").status_code, 403)
            self.assertEqual(self.client.patch(url, {
                "name" if resource else "title": "Unauthorized",
            }, format="json").status_code, 403)
            self.assertEqual(self.client.delete(url).status_code, 403)

    def test_owner_and_admin_grant_and_revoke_only_shared_library_management(self):
        baseline = get_effective_access(self.employee)
        url = self.base + f"permissions/{self.employee.pk}/"
        self.assertFalse(self.client.get(self.base + "permissions/").json()["canManageShared"])
        self.assertEqual(self.create(scope="SHARED").status_code, 403)
        for manager in (self.owner_client, self.admin_client):
            self.assertEqual(manager.patch(url, {"granted": True}, format="json").status_code, 200)
            self.assertTrue(self.client.get(self.base + "permissions/").json()["canManageShared"])
            created = self.create(scope="SHARED", title=f"By {id(manager)}")
            self.assertEqual(created.status_code, 201)
            template_url = self.base + f"{created.json()['template']['id']}/"
            self.assertEqual(self.client.patch(template_url, {"text": "Shared edit"}, format="json").status_code, 200)
            for resource in ("categories/", "tags/"):
                item = self.create(resource=resource, scope="SHARED", name=f"By {id(manager)}")
                self.assertEqual(item.status_code, 201)
                item_url = self.base + resource + f"{item.json()['item']['id']}/"
                self.assertEqual(self.client.patch(item_url, {"name": "Edited"}, format="json").status_code, 200)
                self.assertEqual(self.client.delete(item_url).status_code, 204)
            self.assertEqual(get_effective_access(self.employee), baseline)
            # A real unrelated settings endpoint stays forbidden.
            settings_url = self.base.replace("templates/", "queue-policy/")
            self.assertEqual(self.client.get(settings_url).status_code, 403)
            self.assertEqual(self.client.patch(url, {"granted": False}, format="json").status_code, 403)
            self.assertEqual(self.client.delete(template_url).status_code, 204)
            self.assertEqual(manager.patch(url, {"granted": False}, format="json").status_code, 200)
            self.assertEqual(AuditEvent.objects.filter(
                organization=self.organization, action="conversations.template_management_changed",
                object_id=str(self.employee.pk),
            ).order_by("-pk").first().payload, {"granted": False})
            self.assertFalse(self.client.get(self.base + "permissions/").json()["canManageShared"])
            self.assertEqual(self.create(scope="SHARED").status_code, 403)
            self.assertEqual(self.create(title=f"Personal {id(manager)}").status_code, 201)

    def test_grant_cannot_be_self_assigned_or_cross_tenant_or_expand_settings(self):
        url = self.base + f"permissions/{self.employee.pk}/"
        self.assertEqual(self.client.patch(url, {"granted": True}, format="json").status_code, 403)
        foreign_url = self.base + f"permissions/{self.foreign_member.pk}/"
        self.assertEqual(self.owner_client.get(foreign_url).status_code, 404)
        self.assertEqual(self.owner_client.patch(foreign_url, {"granted": True}, format="json").status_code, 404)
        for payload in ({"granted": "true"}, {"granted": True, "role": "ADMIN"}, {}):
            self.assertEqual(self.owner_client.patch(url, payload, format="json").status_code, 400)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.role, "EMPLOYEE")

    def test_grant_is_membership_scoped_and_inactive_members_cannot_use_it(self):
        url = self.base + f"permissions/{self.employee.pk}/"
        self.owner_client.patch(url, {"granted": True}, format="json")
        foreign_client = self.client_for(self.foreign_member)
        foreign_url = self.base.replace(str(self.organization.public_id), str(self.foreign.public_id))
        self.assertFalse(foreign_client.get(foreign_url + "permissions/").json()["canManageShared"])
        self.assertEqual(foreign_client.post(foreign_url, {"title": "Shared", "text": "Text"}, format="json").status_code, 403)
        # Test DB only; no real account or credential is changed.
        self.employee.block()
        self.assertEqual(self.create(title="Blocked").status_code, 404)
