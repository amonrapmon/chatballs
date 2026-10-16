from django.db import connection
from django.http import QueryDict

from chatballs.conversations.template_models import (
    ReplyTemplate,
    ReplyTemplateCategory,
    ReplyTemplateTag,
)
from chatballs.conversations.template_search import search_templates
from chatballs.conversations.template_test_base import TemplateTestBase
from chatballs.tenancy.database import tenant_atomic


class TemplateSearchTests(TemplateTestBase):
    def ids(self, params, client=None):
        response = (client or self.client).get(self.base, params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], len(payload["items"]))
        return {item["id"] for item in payload["items"]}

    def test_title_and_text_search_only_counts_visible_libraries(self):
        personal = self.create(title="Delivery", text="Hello").json()["template"]
        shared = self.create(self.owner_client, scope="SHARED", title="Welcome", text="DELIVERY info").json()["template"]
        hidden = self.create(self.colleague_client, title="Delivery secret").json()["template"]
        ReplyTemplate.objects.create(
            organization=self.foreign, owner=self.foreign_member, title="Delivery", text="Delivery secret",
        )
        self.assertEqual(self.ids({"q": " delivery "}), {personal["id"], shared["id"]})
        self.assertEqual(self.ids({"q": "secret"}), set())
        self.assertEqual(self.ids({"q": "delivery", "scope": "PERSONAL"}), {personal["id"]})
        self.assertEqual(self.ids({"q": "delivery", "scope": "SHARED"}), {shared["id"]})
        self.assertEqual(self.ids({"q": "delivery"}, self.owner_client), {shared["id"]})
        self.assertEqual(self.ids({"q": "delivery"}, self.colleague_client), {shared["id"], hidden["id"]})
        cyrillic = self.create(title="Доставка", text="ОПЛАТА заказа").json()["template"]
        self.assertEqual(self.ids({"q": "доставка"}), {cyrillic["id"]})
        self.assertEqual(self.ids({"q": "оплата"}), {cyrillic["id"]})

    def test_pagination_is_stable_for_equal_titles_and_legacy_chooser_keeps_all_items(self):
        personal = self.create(title="Same").json()["template"]
        shared = self.create(self.owner_client, scope="SHARED", title="Same").json()["template"]
        for index in range(21):
            ReplyTemplate.objects.create(
                organization=self.organization, owner=self.employee, title=f"Z {index:02}", text="Text",
            )
        legacy = self.client.get(self.base).json()
        self.assertEqual(set(legacy), {"items"})
        self.assertEqual(len(legacy["items"]), 23)
        default = self.client.get(self.base, {"q": ""}).json()
        self.assertEqual((default["page"], default["pageSize"], default["total"], default["pageCount"]), (1, 20, 23, 2))
        self.assertEqual(len(default["items"]), 20)
        first = self.client.get(self.base, {"pageSize": 1}).json()
        second = self.client.get(self.base, {"pageSize": 1, "page": 2}).json()
        self.assertEqual([first["items"][0]["id"], second["items"][0]["id"]], [personal["id"], shared["id"]])
        final = self.client.get(self.base, {"pageSize": 20, "page": 999}).json()
        self.assertEqual(final["page"], 2)
        self.assertEqual(len(final["items"]), 3)
        self.assertEqual(self.client.get(self.base, {"pageSize": 1000}).json()["pageSize"], 100)

    def test_category_and_all_tags_combine_with_search_and_scope_without_duplicates(self):
        category = self.create(resource="categories/").json()["item"]
        first = self.create(resource="tags/").json()["item"]
        second = self.create(resource="tags/", name="Second").json()["item"]
        both = self.create(title="Both", categoryId=category["id"], tagIds=[first["id"], second["id"]]).json()["template"]
        single = self.create(title="Single", tagIds=[first["id"]]).json()["template"]
        self.assertEqual(self.ids({"categoryId": category["id"]}), {both["id"]})
        self.assertEqual(self.ids({"tagIds": str(first["id"])}), {both["id"], single["id"]})
        for tags in (f"{first['id']},{second['id']},{first['id']}", [str(first["id"]), str(second["id"])]):
            self.assertEqual(self.ids({"tagIds": tags}), {both["id"]})
            self.assertEqual(self.ids({"q": "both", "categoryId": category["id"], "tagIds": tags, "scope": "PERSONAL"}), {both["id"]})
            self.assertEqual(self.ids({"scope": "SHARED", "tagIds": tags}), set())
        self.assertEqual(self.ids({"q": "single", "categoryId": category["id"]}), set())
        self.client.delete(self.base + f"categories/{category['id']}/")
        self.client.delete(self.base + f"tags/{second['id']}/")
        self.assertEqual(self.ids({"tagIds": str(first["id"])}), {both["id"], single["id"]})

    def test_shared_category_and_tags_are_available_to_chat_employee(self):
        category = self.create(self.owner_client, "categories/", "SHARED").json()["item"]
        tag = self.create(self.owner_client, "tags/", "SHARED").json()["item"]
        shared = self.create(
            self.owner_client, scope="SHARED", categoryId=category["id"], tagIds=[tag["id"]],
        ).json()["template"]
        self.create()
        self.assertEqual(self.ids({"categoryId": category["id"], "tagIds": tag["id"]}), {shared["id"]})
        self.assertEqual(self.ids({"scope": "PERSONAL", "categoryId": category["id"]}), set())

    def test_filter_ids_and_taxonomy_direct_ids_hide_other_owners_and_tenants(self):
        for resource, model, param in (
            ("categories/", ReplyTemplateCategory, "categoryId"),
            ("tags/", ReplyTemplateTag, "tagIds"),
        ):
            hidden = self.create(self.colleague_client, resource).json()["item"]["id"]
            foreign = model.objects.create(organization=self.foreign, owner=self.foreign_member, name="Secret")
            missing = max(hidden, foreign.pk) + 1000
            for client in (self.client, self.owner_client):
                expected = client.get(self.base, {param: missing})
                self.assertEqual(expected.status_code, 404)
                for pk in (hidden, foreign.pk):
                    with self.subTest(resource=resource, pk=pk):
                        response = client.get(self.base, {param: pk, "q": "no match"})
                        self.assertEqual(response.status_code, 404)
                        self.assertEqual(response.json(), expected.json())
                        url = self.base + resource + f"{pk}/"
                        self.assertEqual(client.get(url).status_code, 404)
                        self.assertEqual(client.patch(url, {"name": "Changed"}, format="json").status_code, 404)
                        self.assertEqual(client.delete(url).status_code, 404)

    def test_invalid_filters_and_pagination_are_rejected(self):
        for params in (
            {"scope": "UNKNOWN"}, {"categoryId": "bad"}, {"categoryId": 0},
            {"tagIds": "1,bad"}, {"tagIds": ""}, {"tagIds": -1},
            {"categoryId": 2**63}, {"tagIds": 2**63},
            {"page": 0}, {"page": "bad"}, {"pageSize": -1},
        ):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(self.base, params).status_code, 400)

    def test_search_runs_with_real_runtime_rls_and_membership_scope(self):
        category = self.create(resource="categories/").json()["item"]
        tag = self.create(resource="tags/").json()["item"]
        own = self.create(categoryId=category["id"], tagIds=[tag["id"]]).json()["template"]
        shared = self.create(self.owner_client, scope="SHARED").json()["template"]
        self.create(self.colleague_client)
        ReplyTemplate.objects.create(organization=self.foreign, title="Greeting", text="Foreign")
        with tenant_atomic(self.context):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            self.assertEqual(
                {item.pk for item in search_templates(self.employee, QueryDict("q=Greeting"))},
                {own["id"], shared["id"]},
            )
            self.assertEqual(
                [item.pk for item in search_templates(
                    self.employee, QueryDict(f"categoryId={category['id']}&tagIds={tag['id']}"),
                )], [own["id"]],
            )
