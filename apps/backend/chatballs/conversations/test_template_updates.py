from copy import deepcopy

from django.test import TestCase

from chatballs.ai.skill_runtime_testing import SkillRuntimeSetup
from chatballs.ai.template_runtime_testing import reply_template
from chatballs.conversations.template_updates import add_template_updates


class TemplateHistoryHintTests(SkillRuntimeSetup, TestCase):
    def setUp(self):
        super().setUp()
        self.template = reply_template()
        self.skill.templates = [self.template]
        self.skill.save(update_fields=["templates"])
        self.saved = {"text": "Saved text", "contentHtml": "<p>Saved card</p>",
                      "deliveryRepresentation": "html", "presentation": {"srcDoc": "Saved document"},
                      "template": {"skillId": str(self.skill.public_id), "skillRevision": self.skill.revision,
                                   "id": self.template["id"], "name": "Original name"}}

    def test_known_new_revision_adds_only_hint_without_rebuilding_or_renaming_snapshot(self):
        items = [deepcopy(self.saved), deepcopy(self.saved)]
        with self.assertNumQueries(1):
            add_template_updates(items, organization_id=self.organization.pk)
        self.assertEqual(items[0], self.saved)
        self.skill.revision += 1
        self.skill.templates[0]["name"] = "Renamed"
        self.skill.save(update_fields=["revision", "templates", "updated_at"])
        with self.assertNumQueries(1):
            add_template_updates(items, organization_id=self.organization.pk)
        for item in items:
            self.assertEqual(item.pop("templateUpdatedAt"), self.skill.updated_at.isoformat())
            self.assertEqual(item, self.saved)

    def test_deleted_template_or_skill_and_other_tenant_leave_snapshot_readable(self):
        self.skill.revision += 1
        self.skill.templates = []
        self.skill.save(update_fields=["revision", "templates"])
        for organization_id in [self.organization.pk, self.organization.pk + 999]:
            items = [deepcopy(self.saved)]
            add_template_updates(items, organization_id=organization_id)
            self.assertEqual(items, [self.saved])
        self.skill.delete()
        items = [deepcopy(self.saved)]
        add_template_updates(items, organization_id=self.organization.pk)
        self.assertEqual(items, [self.saved])

    def test_plain_text_delivery_and_damaged_reference_do_not_read_skill_configuration(self):
        items = [{**self.saved, "deliveryRepresentation": "text"},
                 {**self.saved, "template": {"skillId": "invalid", "skillRevision": 1}}]
        with self.assertNumQueries(0):
            add_template_updates(items, organization_id=self.organization.pk)
        self.assertTrue(all("templateUpdatedAt" not in item for item in items))
