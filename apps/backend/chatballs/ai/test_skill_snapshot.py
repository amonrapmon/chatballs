import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase

from chatballs.ai.provider.base import ToolSpec
from chatballs.ai.pseudonymization import Pseudonymizer
from chatballs.ai.skill_runtime_testing import SkillRuntimeSetup
from chatballs.ai.skills_models import AgentSkill, Skill
from chatballs.ai.tool_loop_testing import ScriptedProvider, says
from chatballs.ai.turn_skills import (
    LOAD_SKILL,
    MAX_CATALOG_BYTES,
    MAX_INSTRUCTION_BYTES,
    MAX_SKILLS,
    plan_turn_skills,
)
from chatballs.ai.turn_tools import TurnTool
from chatballs.tenancy.database import tenant_atomic


class SkillSnapshotTests(SkillRuntimeSetup, TransactionTestCase):
    def test_catalog_is_metadata_only_and_instructions_load_by_choice(self):
        other = self.attach(name="Другой", instruction="Never auto-inject this instruction")
        plan = self.plan(ScriptedProvider(says("Ответ")))
        sent = repr(plan.job.messages)
        for item in (self.skill, other):
            self.assertNotIn(item.instruction, sent)
            self.assertNotIn(item.instruction, repr(plan))
        catalog = json.loads(plan.skills.catalog())
        self.assertEqual({row["id"] for row in catalog}, {str(self.skill.public_id), str(other.public_id)})
        self.assertTrue(all(set(row) == {"id", "name", "description"} for row in catalog))
        self.assertIn(self.skill.name, sent)
        self.assertEqual(plan.tools, [])
        self.assertEqual([tool.name for tool in plan.job.tools], [LOAD_SKILL])
        self.assertEqual(json.loads(plan.skills.load({"skill_id": str(self.skill.public_id)}, plan.pseudonymizer)),
                         {"instruction": self.skill.instruction})

    def test_snapshot_survives_committed_edit_detach_and_delete_until_next_turn(self):
        plan = self.plan(ScriptedProvider(says("Ответ")))

        def change(detach=False):
            close_old_connections()
            try:
                with tenant_atomic(self.context):
                    if detach:
                        AgentSkill.objects.filter(skill=self.skill).delete()
                    else:
                        Skill.objects.filter(pk=self.skill.pk).update(name="Changed", instruction="Changed instruction")
            finally:
                connections["default"].close()

        # Another database connection commits while the planned turn is alive.
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(change).result(timeout=30)
            next_plan = self.plan(ScriptedProvider(says("Ответ")))
            self.assertEqual(next_plan.skills.items[0].instruction, "Changed instruction")
            executor.submit(change, True).result(timeout=30)
        with self.assertNumQueries(0):
            self.assertIn(self.skill.instruction, plan.skills.load(
                {"skill_id": str(self.skill.public_id)}, plan.pseudonymizer))
        self.assertNotIn("Changed", plan.skills.catalog())
        self.assertEqual(self.plan(ScriptedProvider(says("Ответ"))).skills.items, ())
        self.skill.delete()
        self.assertIn(self.skill.instruction, plan.skills.load(
            {"skill_id": str(self.skill.public_id)}, plan.pseudonymizer))

    def test_foreign_unassigned_and_unknown_ids_are_indistinguishable(self):
        foreign = self.attach(agent=self.foreign_agent, instruction="FOREIGN SECRET")
        unassigned = self.attach(agent=self.agents[1], instruction="UNASSIGNED SECRET")
        plan = self.plan(ScriptedProvider(says("Ответ")))
        for id_ in (str(foreign.public_id), str(unassigned.public_id), str(uuid.uuid4())):
            with self.assertNumQueries(0):
                self.assertEqual(json.loads(plan.skills.load({"skill_id": id_}, plan.pseudonymizer)),
                                 {"error": "skill_unavailable"})
        self.assertNotIn("SECRET", repr(plan.job))

    def test_real_runtime_role_obeys_tenant_context(self):
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE chatballs_runtime_app")
        try:
            for tenant, expected in ((self.organization.pk, 1), (self.other.pk, 0)):
                with tenant_atomic(tenant):
                    snapshot = plan_turn_skills(self.agent, [], Pseudonymizer())
                    self.assertEqual(len(snapshot.items), expected)
            self.assertEqual(plan_turn_skills(self.agent, [], Pseudonymizer()).items, ())
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def test_external_names_never_shadow_internal_load(self):
        names = [LOAD_SKILL, f"{LOAD_SKILL}_1"]
        tools = [TurnTool(ToolSpec(name=name, description="External"), None, name) for name in names]
        with tenant_atomic(self.context):
            snapshot = plan_turn_skills(self.agent, tools, Pseudonymizer())
        self.assertEqual(snapshot.operation, f"{LOAD_SKILL}_2")

    def test_snapshot_and_masked_payload_limits_fail_closed(self):
        provider = ScriptedProvider(says("Ответ"))
        with patch("chatballs.ai.turn_skills.MAX_SKILLS", 0):
            self.assertFalse(self.plan(provider).skills.enabled)
        with patch("chatballs.ai.turn_skills.MAX_CATALOG_BYTES", 1):
            self.assertFalse(self.plan(provider).skills.enabled)
        plan = self.plan(provider)
        with patch("chatballs.ai.turn_skills.MAX_INSTRUCTION_BYTES", 1):
            self.assertEqual(json.loads(plan.skills.load({"skill_id": str(self.skill.public_id)}, plan.pseudonymizer)),
                             {"error": "skill_too_large"})
        self.assertEqual((MAX_SKILLS, MAX_CATALOG_BYTES, MAX_INSTRUCTION_BYTES), (100, 65536, 262144))
