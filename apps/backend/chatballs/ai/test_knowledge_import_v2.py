import json

from django.test import TestCase

from chatballs.ai.knowledge_categories import create_category
from chatballs.ai.knowledge_policy_test_base import KnowledgePolicyTestBase
from chatballs.ai.knowledge_types import UNCATEGORIZED_CATEGORY_NAME
from chatballs.ai.models import AIAgent, AIAgentStatus, Knowledge, KnowledgeCategory
from chatballs.channels.models import Channel
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.testing import TenantAPIClient, system_tenant_context


class KnowledgeMetadataImportTests(TestCase):
    def setUp(self) -> None:
        result = bootstrap_owner(
            email="owner@example.com",
            password="temporary-password",
        )
        self.organization = result.organization
        self.context = system_tenant_context(self.organization)
        self.products = create_category(
            context=self.context,
            name="Products",
        )
        self.app = create_category(
            context=self.context,
            name="Acme",
            parent=self.products,
        )
        self.client = TenantAPIClient()
        self.client.login(
            username="owner@example.com",
            password="temporary-password",
        )

    def _import(self, documents: list[object]):
        return self.client.post(
            "/api/v1/ai/knowledge/import/",
            data=json.dumps({"documents": documents}),
            content_type="application/json",
        )

    def test_legacy_document_uses_uncategorized_default(self) -> None:
        response = self._import([{"title": "Legacy", "content": "Legacy text"}])

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["created"], 1)
        knowledge = Knowledge.objects.get(title="Legacy")
        self.assertEqual(knowledge.category.name, UNCATEGORIZED_CATEGORY_NAME)

    def test_explicit_category_path_is_imported(self) -> None:
        response = self._import(
            [
                {
                    "title": "Acme support",
                    "description": "Support rules",
                    "categoryPath": ["Products", "Acme"],
                    "content": "Procedure",
                }
            ]
        )

        self.assertEqual(response.json()["created"], 1)
        knowledge = Knowledge.objects.get(title="Acme support")
        self.assertEqual(knowledge.category_id, self.app.id)

    def test_missing_category_is_created_under_existing_parent(self) -> None:
        response = self._import(
            [
                {
                    "title": "Unknown path",
                    "categoryPath": ["Products", "Missing"],
                    "content": "No",
                },
                {"title": "Valid", "content": "Yes"},
            ]
        )

        payload = response.json()
        self.assertEqual(payload["created"], 2)
        self.assertEqual(payload["failed"], [])
        category = KnowledgeCategory.objects.get(
            organization=self.organization, parent=self.products, name="Missing"
        )
        self.assertEqual(Knowledge.objects.get(title="Unknown path").category_id, category.id)

    def test_new_tree_is_shared_and_repeat_import_does_not_duplicate_categories(self) -> None:
        documents = [
            {"title": title, "content": "Text", "categoryPath": [" New root ", "Child", "Leaf"]}
            for title in ["First", "Second"]
        ]
        before = KnowledgeCategory.objects.count()
        self.assertEqual(self._import(documents).json()["created"], 2)
        self.assertEqual(self._import(documents).json()["unchanged"], 2)
        self.assertEqual(KnowledgeCategory.objects.count(), before + 3)
        first = Knowledge.objects.get(title="First")
        second = Knowledge.objects.get(title="Second")
        self.assertEqual(first.category_id, second.category_id)
        self.assertEqual(first.category.parent.parent.name, "New root")

    def test_failed_document_rolls_back_new_categories_and_other_documents_import(self) -> None:
        response = self._import([
            {"title": "Invalid", "content": "Text", "description": [],
             "categoryPath": ["Rollback root", "Child"]},
            {"title": "Valid sibling", "content": "Text", "categoryPath": ["Kept root"]},
        ])
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(len(response.json()["failed"]), 1)
        self.assertFalse(KnowledgeCategory.objects.filter(name="Rollback root").exists())
        self.assertFalse(Knowledge.objects.filter(title="Invalid").exists())

    def test_invalid_path_rolls_back_preceding_levels(self) -> None:
        for path in [["Invalid root", " "], ["Invalid root", 42], []]:
            with self.subTest(path=path):
                response = self._import([{"title": "Invalid path", "content": "Text", "categoryPath": path}])
                self.assertEqual(len(response.json()["failed"]), 1)
                self.assertFalse(KnowledgeCategory.objects.filter(name="Invalid root").exists())

    def test_existing_document_moves_to_new_category(self) -> None:
        self._import([{"title": "Moving", "content": "Text"}])
        response = self._import([
            {"title": "Moving", "content": "Text", "categoryPath": ["New destination"]}
        ])
        self.assertEqual(response.json()["updated"], 1)
        self.assertEqual(Knowledge.objects.get(title="Moving").category.name, "New destination")

    def test_omitted_metadata_preserves_category_and_agent_links(self) -> None:
        self._import(
            [
                {
                    "title": "Preserved",
                    "categoryPath": ["Products", "Acme"],
                    "content": "Version one",
                }
            ]
        )
        knowledge = Knowledge.objects.get(title="Preserved")
        channel = Channel.objects.create(
            organization=self.organization,
            code="import-support",
            name="Import support",
        )
        agent = AIAgent.objects.create(
            channel=channel,
            name="Import agent",
            status=AIAgentStatus.ACTIVE,
        )
        agent.knowledge_items.add(knowledge)

        response = self._import([{"title": "Preserved", "content": "Version two"}])

        self.assertEqual(response.json()["updated"], 1)
        knowledge.refresh_from_db()
        self.assertEqual(knowledge.category_id, self.app.id)
        self.assertTrue(agent.knowledge_items.filter(id=knowledge.id).exists())

    def test_metadata_only_update_keeps_existing_fragments(self) -> None:
        self._import([{"title": "Metadata", "content": "Stable content"}])
        knowledge = Knowledge.objects.get(title="Metadata")
        fragment_ids = list(knowledge.fragments.values_list("id", flat=True))

        response = self._import(
            [
                {
                    "title": "Metadata",
                    "categoryPath": ["Products", "Acme"],
                    "content": "Stable content",
                }
            ]
        )

        self.assertEqual(response.json()["updated"], 1)
        knowledge.refresh_from_db()
        self.assertEqual(knowledge.category_id, self.app.id)
        self.assertEqual(
            list(knowledge.fragments.values_list("id", flat=True)),
            fragment_ids,
        )


class KnowledgeImportPolicyTests(KnowledgePolicyTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.client = TenantAPIClient()
        self.client.force_login(self.employee.user)

    def test_employee_cannot_import_knowledge(self) -> None:
        response = self.client.post(
            "/api/v1/ai/knowledge/import/",
            data=json.dumps(
                {
                    "documents": [
                        {
                            "title": self.support_only.title,
                            "content": "Attempted overwrite",
                            "categoryPath": ["Forbidden category"],
                        }
                    ]
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.support_only.refresh_from_db()
        self.assertEqual(self.support_only.content, "")
        self.assertFalse(KnowledgeCategory.objects.filter(name="Forbidden category").exists())
