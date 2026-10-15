import json
import uuid

from django.test import TestCase

from chatballs.ai.skills_models import AgentSkill, Skill, SkillRequest
from chatballs.ai.skills_test_support import SkillsSetup
from chatballs.ai.skills_validation import INSTRUCTION_MAX, REQUEST_MAX_BYTES
from chatballs.conversations.models import Contact, Conversation, Message
from chatballs.identity.models import AuditEvent


class SkillConfigurationTests(SkillsSetup, TestCase):
    def test_create_read_and_atomic_update_with_retry(self):
        body = {"requestId": str(uuid.uuid4()), "configuration": self.config()}
        first = self.client.post(self.url, body, format="json")
        self.assertEqual(first.status_code, 201, first.content)
        skill = first.json()["skill"]
        again = self.client.post(self.url, body, format="json")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["skill"], skill)
        self.assertEqual(Skill.objects.count(), 1)
        self.assertEqual(skill["templates"], [])
        self.assertEqual(skill["createdBy"]["id"], self.owner.pk)
        self.assertEqual(skill["updatedBy"], skill["createdBy"])
        self.assertTrue(skill["createdAt"] and skill["updatedAt"])
        self.assertEqual(self.client.get(self.detail(skill)).json()["skill"], skill)
        update = {"requestId": str(uuid.uuid4()), "expectedRevision": 1, "configuration": self.config(name="Новое")}
        saved = self.client.put(self.detail(skill), update, format="json")
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertEqual(saved.json()["skill"]["revision"], 2)
        self.assertEqual(saved.json()["skill"]["id"], skill["id"])
        self.assertEqual(self.client.put(self.detail(skill), update, format="json").status_code, 200)
        update["requestId"] = str(uuid.uuid4())
        stale = self.client.put(self.detail(skill), update, format="json")
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "revision_conflict")
        self.assertEqual(AuditEvent.objects.filter(action="ai.skill_updated").count(), 1)

    def test_invalid_configuration_never_replaces_saved_values(self):
        skill = self.create_skill()
        for changes in (
            {"name": ""}, {"name": "x" * 61}, {"description": " "},
            {"description": "x" * 201}, {"instruction": "\n"},
            {"instruction": "x" * (INSTRUCTION_MAX + 1)},
            {"instruction": "invalid\0text"}, {"name": "invalid\0name"},
            {"templates": [{"html": "<script>secret</script>"}]}, {"templates": {}},
            {"surprise": "secret"},
        ):
            with self.subTest(changes=list(changes)):
                response = self.client.put(self.detail(skill), {
                    "requestId": str(uuid.uuid4()), "expectedRevision": 1,
                    "configuration": self.config(**{"name": "Changed", **changes}),
                }, format="json")
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("code", response.json())
                self.assertNotIn("secret", str(response.json()))
        invalid_unicode = self.client.put(self.detail(skill), json.dumps({
            "requestId": str(uuid.uuid4()), "expectedRevision": 1,
            "configuration": self.config(instruction="\ud800"),
        }), content_type="application/json")
        self.assertEqual(invalid_unicode.status_code, 400, invalid_unicode.content)
        self.assertEqual(invalid_unicode.json()["code"], "invalid_field")
        self.assertEqual(self.client.get(self.detail(skill)).json()["skill"], skill)
        self.assertEqual(SkillRequest.objects.count(), 1)

    def test_limits_envelope_and_request_identity(self):
        skill = self.create_skill(name="я" * 60, description="я" * 200, instruction="я" * INSTRUCTION_MAX)
        for revision in (None, True, "1", 0, -1, 2**64):
            response = self.client.delete(self.detail(skill), {"expectedRevision": revision}, format="json")
            self.assertEqual(response.status_code, 400, response.content)
        for body in ({}, {"requestId": "bad", "configuration": self.config()}):
            self.assertEqual(self.client.post(self.url, body, format="json").status_code, 400)
        huge = self.client.post(self.url, {"requestId": str(uuid.uuid4()), "configuration": self.config(instruction="x" * REQUEST_MAX_BYTES)}, format="json")
        self.assertEqual(huge.status_code, 413)
        key = str(uuid.uuid4())
        self.assertEqual(self.client.post(self.url, {"requestId": key, "configuration": self.config()}, format="json").status_code, 201)
        conflict = self.client.post(self.url, {"requestId": key, "configuration": self.config(name="Other")}, format="json")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["code"], "request_conflict")

    def test_search_pagination_and_metadata(self):
        for i in range(4):
            self.create_skill(name=f"Навык {i}", description="Особое условие" if i == 2 else "Общее")
        page = self.client.get(self.url, {"pageSize": 2, "page": 2}).json()
        self.assertEqual((page["total"], page["pageCount"], page["page"], len(page["items"])), (4, 2, 2, 2))
        for query in ("навык 2", "особое"):
            found = self.client.get(self.url, {"q": query, "pageSize": 1}).json()
            self.assertEqual(found["total"], 1)
            self.assertEqual(found["items"][0]["name"], "Навык 2")
            self.assertNotIn("instruction", found["items"][0])
        self.assertEqual(self.client.get(self.url, {"q": "missing"}).json()["total"], 0)
        for params in ({"q": "invalid\0query"}, {"page": "bad"}):
            self.assertEqual(self.client.get(self.url, params).status_code, 400)

    def test_assign_detach_delete_confirmation_audit_and_deleted_retry(self):
        key = str(uuid.uuid4())
        body = {"requestId": key, "configuration": self.config(instruction="SECRET-INSTRUCTION")}
        skill = self.client.post(self.url, body, format="json").json()["skill"]
        for i, agent in enumerate(self.agents):
            attached = self.client.put(self.assignment(skill, agent), {"expectedRevision": i + 1}, format="json")
            self.assertEqual(attached.status_code, 200, attached.content)
            self.assertEqual(self.client.put(self.assignment(skill, agent), {"expectedRevision": i + 1}, format="json").status_code, 200)
        self.assertEqual(AgentSkill.objects.count(), 2)
        contact = Contact.objects.create(organization=self.organization)
        conversation = Conversation.objects.create(organization=self.organization, channel=self.agents[1].channel, contact=contact)
        message = Message.objects.create(conversation=conversation, author_type="AI", text="Saved reply", content_html="<p>Saved reply</p>")
        detached = self.client.delete(self.assignment(skill, self.agents[0]), {"expectedRevision": 3}, format="json")
        self.assertEqual(detached.status_code, 200)
        self.assertEqual(detached.json()["skill"]["agents"][0]["id"], self.agents[1].channel_id)
        preview = self.client.get(self.detail(skill) + "deletion/").json()
        self.assertTrue(preview["confirmationRequired"])
        self.assertEqual(preview["skill"]["agentCount"], 1)
        self.assertEqual(preview["skill"]["templateCount"], 0)
        self.assertNotIn("instruction", preview["skill"])
        stale = self.client.delete(self.detail(skill), {"expectedRevision": 3}, format="json")
        self.assertEqual(stale.status_code, 409)
        deleted = self.client.delete(self.detail(skill), {"expectedRevision": 4}, format="json")
        self.assertEqual(deleted.status_code, 204, deleted.content)
        self.assertFalse(Skill.objects.exists())
        self.assertFalse(AgentSkill.objects.exists())
        message.refresh_from_db()
        self.assertEqual((message.text, message.content_html), ("Saved reply", "<p>Saved reply</p>"))
        self.assertEqual(SkillRequest.objects.count(), 1)
        self.assertEqual(self.client.post(self.url, body, format="json").status_code, 404)
        events = AuditEvent.objects.filter(object_id=skill["id"])
        self.assertEqual(set(events.values_list("action", flat=True)), {"ai.skill_created", "ai.skill_attached", "ai.skill_detached", "ai.skill_deleted"})
        for event in events:
            self.assertEqual(event.actor_id, self.owner.pk)
            self.assertEqual(event.organization_id, self.organization.pk)
            self.assertLessEqual(set(event.payload), {"revision", "agentId", "agentIds"})
            self.assertNotIn("SECRET", str(event.payload))
