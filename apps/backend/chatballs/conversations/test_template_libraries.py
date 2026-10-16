from chatballs.conversations.template_models import ReplyTemplate
from chatballs.conversations.template_test_base import TemplateTestBase


class TemplateLibraryTests(TemplateTestBase):
    def test_titles_are_unique_per_library_and_personal_owner(self):
        for client, scope in (
            (self.owner_client, "SHARED"), (self.client, "PERSONAL"),
            (self.colleague_client, "PERSONAL"),
        ):
            with self.subTest(scope=scope):
                created = self.create(client, scope=scope)
                self.assertEqual(created.status_code, 201)
                self.assertEqual(self.create(client, scope=scope, title="greeting").status_code, 409)
                url = self.base + str(created.json()["template"]["id"]) + "/"
                self.assertEqual(client.patch(url, {"title": "GREETING"}, format="json").status_code, 200)
        personal = self.create(title="Other").json()["template"]
        self.assertEqual(self.client.patch(
            self.base + f"{personal['id']}/", {"title": "greeting"}, format="json",
        ).status_code, 409)

    def test_foreign_personal_and_tenant_ids_are_hidden_for_every_operation(self):
        own = self.create().json()["template"]
        shared = self.create(self.owner_client, scope="SHARED").json()["template"]
        foreign = ReplyTemplate.objects.create(
            organization=self.foreign, owner=self.foreign_member, title="Foreign", text="Secret",
        )
        for client, hidden_id in (
            (self.colleague_client, own["id"]), (self.owner_client, own["id"]),
            (self.client, foreign.pk),
        ):
            with self.subTest(hidden_id=hidden_id):
                self.assertNotIn(hidden_id, [x["id"] for x in client.get(self.base).json()["items"]])
                url = self.base + f"{hidden_id}/"
                self.assertEqual(client.get(url).status_code, 404)
                self.assertEqual(client.patch(url, {"text": "Changed"}, format="json").status_code, 404)
                self.assertEqual(client.delete(url).status_code, 404)
        self.assertEqual({x["id"] for x in self.client.get(self.base).json()["items"]}, {own["id"], shared["id"]})
        self.assertEqual(self.client.get(self.base + f"{own['id']}/").status_code, 200)
        self.assertEqual(self.client.patch(self.base + f"{own['id']}/", {"text": "Mine"}, format="json").status_code, 200)
        self.assertEqual(self.client.delete(self.base + f"{own['id']}/").status_code, 204)

    def test_membership_not_global_user_owns_personal_library(self):
        own = self.create().json()["template"]
        foreign_client = self.client_for(self.foreign_member)
        foreign_base = self.base.replace(str(self.organization.public_id), str(self.foreign.public_id))
        response = foreign_client.post(foreign_base, {
            "scope": "PERSONAL", "title": own["title"], "text": "Other organization",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["template"]["ownerId"], self.foreign_member.pk)
        self.assertEqual(foreign_client.get(foreign_base + f"{own['id']}/").status_code, 404)

    def test_scope_and_owner_cannot_be_supplied_or_changed(self):
        own = self.create().json()["template"]
        url = self.base + f"{own['id']}/"
        for data in ({"scope": "SHARED"}, {"ownerId": self.colleague.pk}, {"organizationId": self.foreign.pk}):
            self.assertEqual(self.client.patch(url, data, format="json").status_code, 400)
        self.assertEqual(self.create(scope="UNKNOWN").status_code, 400)
        self.assertEqual(self.create(title="Wrong", ownerId=self.colleague.pk).status_code, 400)
