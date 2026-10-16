import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections
from django.test import TransactionTestCase

from chatballs.ai.skills_models import Skill, SkillRequest
from chatballs.ai.skills_service import save_configuration
from chatballs.ai.skills_test_support import SkillsSetup
from chatballs.ai.skills_validation import SkillError
from chatballs.identity.models import AuditEvent


class SkillConcurrencyTests(SkillsSetup, TransactionTestCase):
    def parallel(self, calls):
        barrier = threading.Barrier(len(calls))

        def run(call):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return call()
            except SkillError as error:
                return error.status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            return list(pool.map(run, calls))

    def test_simultaneous_create_retry_commits_one_configuration_and_audit(self):
        key = uuid.uuid4()

        def create():
            skill, created = save_configuration(context=self.context, raw=self.config(), request_id=key)
            return str(skill.public_id), created

        results = self.parallel([create, create])
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sorted(item[1] for item in results), [False, True])
        self.assertEqual(Skill.objects.count(), 1)
        self.assertEqual(SkillRequest.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action="ai.skill_created").count(), 1)

    def test_simultaneous_edit_requires_reload_instead_of_overwriting(self):
        skill = self.create_skill()

        def edit(name):
            updated, _ = save_configuration(
                context=self.context, raw=self.config(name=name), request_id=uuid.uuid4(),
                public_id=skill["id"], revision=1,
            )
            return updated.revision

        results = self.parallel([lambda: edit("First"), lambda: edit("Second")])
        self.assertEqual(sorted(results), [2, 409])
        self.assertEqual(Skill.objects.get().revision, 2)
        self.assertEqual(AuditEvent.objects.filter(action="ai.skill_updated").count(), 1)
