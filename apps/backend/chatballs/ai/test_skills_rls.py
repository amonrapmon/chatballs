import uuid

from django.db import DatabaseError, connection
from django.test import TransactionTestCase

from chatballs.ai.skills_models import AgentSkill, Skill, SkillRequest
from chatballs.ai.skills_test_support import SkillsSetup
from chatballs.tenancy.database import tenant_atomic


class SkillRuntimeRoleTests(SkillsSetup, TransactionTestCase):
    def as_app(self, call):
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE chatballs_runtime_app")
        try:
            return call()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def test_runtime_role_full_lifecycle_and_tenant_visibility(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT rolsuper, rolbypassrls, pg_has_role(rolname, 'chatballs_schema', 'MEMBER') FROM pg_roles WHERE rolname = 'chatballs_runtime_app'")
            self.assertEqual(cursor.fetchone(), (False, False, False))
        skill = self.as_app(self.create_skill)
        attached = self.as_app(lambda: self.client.put(
            self.assignment(skill, self.agents[0]), {"expectedRevision": 1}, format="json",
        ))
        self.assertEqual(attached.status_code, 200, attached.content)
        for organization, expected in ((self.organization, (1, 1, 1)), (self.other, (0, 0, 0))):
            with tenant_atomic(organization.pk):
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
                self.assertEqual(tuple(model.objects.count() for model in (Skill, AgentSkill, SkillRequest)), expected)
        self.assertEqual(self.as_app(lambda: self.client.get(self.url)).json()["total"], 1)
        updated = self.as_app(lambda: self.client.put(self.detail(skill), {
            "expectedRevision": 2, "requestId": str(uuid.uuid4()), "configuration": self.config(name="Updated"),
        }, format="json"))
        self.assertEqual(updated.status_code, 200, updated.content)
        deleted = self.as_app(lambda: self.client.delete(self.detail(skill), {"expectedRevision": 3}, format="json"))
        self.assertEqual(deleted.status_code, 204, deleted.content)
        self.assertFalse(AgentSkill.objects.exists())
        self.assertEqual(SkillRequest.objects.count(), 2)

    def insert(self, tenant, row):
        with tenant_atomic(tenant.pk):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            type(row).objects.bulk_create([row])

    def test_rls_and_fk_guards_block_forged_rows_and_duplicate_assignments(self):
        payload = self.create_skill()
        skill = Skill.objects.get(public_id=payload["id"])
        rows = [
            AgentSkill(organization=self.other, skill=skill, agent=self.foreign_agent),
            AgentSkill(organization=self.other, skill=skill, agent=self.agents[0]),
            AgentSkill(organization=self.other, skill=Skill.objects.create(organization=self.other, name="Other", description="Other", instruction="Other"), agent=self.agents[0]),
            AgentSkill(organization=self.organization, skill=skill, agent=self.agents[0]),
            Skill(organization=self.organization, name="Forged", description="x", instruction="x"),
            SkillRequest(organization=self.organization, key=uuid.uuid4(), fingerprint="x", skill_public_id=skill.public_id, result_revision=1),
        ]
        for row in rows:
            with self.subTest(model=type(row).__name__), self.assertRaises(DatabaseError):
                self.insert(self.other, row)
        assignment = AgentSkill(organization=self.organization, skill=skill, agent=self.agents[0])
        self.insert(self.organization, assignment)
        with self.assertRaises(DatabaseError):
            self.insert(self.organization, AgentSkill(organization=self.organization, skill=skill, agent=self.agents[0]))
        self.assertEqual(AgentSkill.objects.count(), 1)

    def test_no_context_platform_and_foreign_updates_are_denied(self):
        payload = self.create_skill()
        for role in ("chatballs_runtime_app", "chatballs_runtime_platform"):
            with tenant_atomic(self.other.pk):
                with connection.cursor() as cursor:
                    cursor.execute(f"SET LOCAL ROLE {role}")
                if role == "chatballs_runtime_platform":
                    with self.assertRaises(DatabaseError):
                        Skill.objects.count()
                else:
                    self.assertEqual(Skill.objects.filter(public_id=payload["id"]).update(name="Forged"), 0)
        self.assertEqual(self.as_app(lambda: Skill.objects.count()), 0)
        self.assertEqual(Skill.objects.get().name, payload["name"])

    def test_owner_author_and_content_constraints_survive_bulk_sql(self):
        payload = self.create_skill()
        for changes in ({"organization": self.other}, {"public_id": uuid.uuid4()}, {"name": "  "}, {"instruction": ""}, {"revision": 0}):
            with self.subTest(changes=list(changes)), self.assertRaises(DatabaseError), tenant_atomic(self.organization.pk):
                Skill.objects.filter(public_id=payload["id"]).update(**changes)
        with self.assertRaises(DatabaseError), tenant_atomic(self.other.pk):
            Skill.objects.bulk_create([Skill(organization=self.other, name="x", description="x", instruction="x", created_by=self.owner)])
