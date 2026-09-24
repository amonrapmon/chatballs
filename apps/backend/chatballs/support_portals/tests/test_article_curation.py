import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command

from chatballs.support_portals.tests.base import SupportPortalTestCase


class ArticleCurationTests(SupportPortalTestCase):
    def setUp(self) -> None:
        super().setUp()
        portal = self.create_portal().json()["portal"]
        self.portal_id = portal["id"]
        self.portal_host = portal["hostedDomain"]
        self.root = self._category("Начало", "start")
        self.child = self._category("Продолжение", "next", parent_id=self.root)

    def _category(self, name: str, slug: str, *, parent_id: int | None = None) -> int:
        payload = {"name": name, "slug": slug}
        if parent_id is not None:
            payload["parentId"] = parent_id
        response = self.client.post(
            f"/api/v1/support/portals/{self.portal_id}/categories/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["category"]["id"]

    def _article(self, slug: str, title: str, category_id: int) -> int:
        response = self.client.post(
            f"/api/v1/support/portals/{self.portal_id}/articles/",
            {
                "categoryId": category_id,
                "slug": slug,
                "title": title,
                "summary": title,
                "content": title,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        article = response.json()["article"]
        published = self.client.post(
            f"/api/v1/support/portals/{self.portal_id}/articles/{article['id']}/publish/",
            {"revisionId": article["revisions"][0]["id"]},
            format="json",
        )
        self.assertEqual(published.status_code, 200, published.content)
        return article["id"]

    def test_order_related_articles_and_direct_category(self) -> None:
        first = self._article("first", "Альфа", self.root)
        second = self._article("second", "Бета", self.root)
        child = self._article("child", "Гамма", self.child)
        base = f"/api/v1/support/portals/{self.portal_id}/articles/"
        for article_id, data in (
            (first, {"sortOrder": 2, "relatedArticleIds": [child, second]}),
            (second, {"sortOrder": 1}),
        ):
            response = self.client.patch(
                f"{base}{article_id}/", data, format="json"
            )
            self.assertEqual(response.status_code, 200, response.content)
        invalid = self.client.patch(
            f"{base}{first}/",
            {"relatedArticleIds": [first]},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)
        self.client.post(
            f"/api/v1/support/portals/{self.portal_id}/status/",
            {"status": "PUBLISHED"},
            format="json",
        )
        self.client.logout()
        listing = self.client.get(
            "/api/v1/help/articles/?category=start&direct=1",
            HTTP_HOST=self.portal_host,
        )
        self.assertEqual(listing.status_code, 200, listing.content)
        self.assertEqual(
            [item["slug"] for item in listing.json()["items"]],
            ["second", "first"],
        )
        detail = self.client.get(
            "/api/v1/help/articles/first/", HTTP_HOST=self.portal_host
        )
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(
            [item["slug"] for item in detail.json()["article"]["relatedArticles"]],
            ["child", "second"],
        )

    def test_curation_command_dry_run_and_apply(self) -> None:
        first = self._article("first", "Альфа", self.root)
        second = self._article("second", "Бета", self.root)
        self.client.post(
            f"/api/v1/support/portals/{self.portal_id}/status/",
            {"status": "PUBLISHED"},
            format="json",
        )
        plan = json.dumps({
            "portal": "app-help",
            "locale": "ru",
            "order": {"start": ["second", "first"]},
            "related": {"first": ["second"], "second": ["first"]},
        })
        output = StringIO()
        with patch("sys.stdin", StringIO(plan)):
            call_command(
                "apply_portal_curation", host=self.portal_host, file="-", stdout=output
            )
        self.assertIn("Would update 2 articles", output.getvalue())
        output = StringIO()
        with patch("sys.stdin", StringIO(plan)):
            call_command(
                "apply_portal_curation", host=self.portal_host, file="-", apply=True,
                stdout=output,
            )
        self.assertIn("Updated 2 articles", output.getvalue())
        self.client.logout()
        listing = self.client.get(
            "/api/v1/help/articles/?category=start&direct=1",
            HTTP_HOST=self.portal_host,
        )
        self.assertEqual(
            [item["slug"] for item in listing.json()["items"]],
            ["second", "first"],
        )
        detail = self.client.get(
            "/api/v1/help/articles/first/", HTTP_HOST=self.portal_host
        )
        self.assertEqual(
            [item["slug"] for item in detail.json()["article"]["relatedArticles"]],
            ["second"],
        )
        self.assertNotEqual(first, second)
