from chatballs.conversations.template_models import (
    ReplyTemplate,
    ReplyTemplateCategory,
    ReplyTemplateTag,
)
from chatballs.conversations.template_test_base import TemplateTestBase


class TemplateTaxonomyTests(TemplateTestBase):
    def test_scoped_taxonomy_crud_uniqueness_and_private_access(self):
        for resource in ("categories/", "tags/"):
            for client, scope in ((self.owner_client, "SHARED"), (self.client, "PERSONAL"), (self.colleague_client, "PERSONAL")):
                created = self.create(client, resource, scope)
                self.assertEqual(created.status_code, 201)
                self.assertEqual(self.create(client, resource, scope, name="greeting").status_code, 409)
            private_id = self.client.get(self.base + resource).json()["items"][1]["id"]
            # Sorting two equal names uses their IDs: shared was created first.
            url = self.base + resource + f"{private_id}/"
            for client in (self.owner_client, self.colleague_client):
                self.assertEqual(client.get(url).status_code, 404)
                self.assertEqual(client.patch(url, {"name": "Changed"}, format="json").status_code, 404)
                self.assertEqual(client.delete(url).status_code, 404)
            self.assertEqual(self.client.patch(url, {"name": "Mine"}, format="json").status_code, 200)
            self.assertEqual(self.client.delete(url).status_code, 204)

    def test_links_require_same_tenant_scope_and_owner_and_deletion_preserves_template(self):
        category = self.create(resource="categories/").json()["item"]
        tag = self.create(resource="tags/").json()["item"]
        template = self.create(categoryId=category["id"], tagIds=[tag["id"], tag["id"]]).json()["template"]
        url = self.base + f"{template['id']}/"
        self.assertEqual(template["categoryId"], category["id"])
        self.assertEqual(template["tagIds"], [tag["id"]])
        for client, scope in ((self.owner_client, "SHARED"), (self.colleague_client, "PERSONAL")):
            wrong_category = self.create(client, "categories/", scope, name="Other").json()["item"]
            wrong_tag = self.create(client, "tags/", scope, name="Other").json()["item"]
            self.assertEqual(self.client.patch(url, {"categoryId": wrong_category["id"]}, format="json").status_code, 400)
            self.assertEqual(self.client.patch(url, {"tagIds": [wrong_tag["id"]]}, format="json").status_code, 400)
        foreign_category = ReplyTemplateCategory.objects.create(organization=self.foreign, name="Foreign")
        foreign_tag = ReplyTemplateTag.objects.create(organization=self.foreign, name="Foreign")
        for data in ({"categoryId": foreign_category.pk}, {"tagIds": [foreign_tag.pk]}, {"tagIds": "bad"}, {"categoryId": True}):
            self.assertEqual(self.client.patch(url, data, format="json").status_code, 400)
        self.assertEqual(self.client.delete(self.base + f"categories/{category['id']}/").status_code, 204)
        self.assertEqual(self.client.delete(self.base + f"tags/{tag['id']}/").status_code, 204)
        preserved = self.client.get(url).json()["template"]
        self.assertIsNone(preserved["categoryId"])
        self.assertEqual(preserved["tagIds"], [])
        self.assertEqual(preserved["text"], template["text"])
        self.assertTrue(ReplyTemplate.objects.filter(pk=template["id"]).exists())

    def test_links_can_be_replaced_and_cleared(self):
        category = self.create(resource="categories/").json()["item"]
        first = self.create(resource="tags/").json()["item"]
        second = self.create(resource="tags/", name="Second").json()["item"]
        template = self.create(categoryId=category["id"], tagIds=[first["id"]]).json()["template"]
        url = self.base + f"{template['id']}/"
        updated = self.client.patch(url, {"tagIds": [second["id"]]}, format="json")
        self.assertEqual(updated.json()["template"]["tagIds"], [second["id"]])
        cleared = self.client.patch(url, {"categoryId": None, "tagIds": []}, format="json")
        self.assertIsNone(cleared.json()["template"]["categoryId"])
        self.assertEqual(cleared.json()["template"]["tagIds"], [])
