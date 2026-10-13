"""Worker contracts against real storage; provider replies isolated at unit boundary."""

import json
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.utils import timezone
from django.test import override_settings
from django.db import transaction

from chatballs.ai.models import AIAgent, LlmInvocation
from chatballs.ai.provider.base import ChatResult, ProviderError
from chatballs.ai.provider.demo import DemoProvider
from chatballs.ai.pseudonymization import Pseudonymizer
from chatballs.conversations.domain_events import record_fact
from chatballs.conversations.models import ConversationComment, MessageAuthor
from chatballs.conversations.models import Conversation
from chatballs.conversations.lifecycle_services import close_conversation
from chatballs.conversations.inactivity_services import close_inactive_locked
from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.integrations.models import Integration
from chatballs.testing import system_tenant_context

from .models import QualityJob, QualityResult
from .queue import QUALITY_REQUESTED
from .test_base import QualityTestBase
from .validation import InvalidQualityOutput, validate_output
from .worker import _prepare, run_quality_analysis


@override_settings(CHATBALLS_AI_PROVIDER="")
class ExecutionTests(QualityTestBase):
    def setUp(self):
        self.configure()
        self.public = self.message(text="Customer customer@example.test +7 999 111-22-33")
        self.message(author_type=MessageAuthor.SYSTEM, text="Secret transfer reason")
        ConversationComment.objects.create(
            organization=self.organization, conversation=self.conversation, author=self.context.actor_user,
            audience="INTERNAL", text="Private consultation", operation_id=uuid4(),
        )
        self.provider = Integration.objects.create(
            organization=self.organization, kind="LLM_PROVIDER", provider="DEMO", name="Quality Demo",
            secret="demo", config={"default_model": "demo"},
        )
        self.agent = AIAgent.objects.create(organization=self.organization, channel=self.conversation.channel,
                                          name="Quality", model="demo", provider_integration=self.provider)
        self.worker_context = system_tenant_context(self.organization)

    def output(self, **changes):
        return {"conclusions": [{"code": "resolution", "value": 1, "explanation": "Evidence",
                                 "recommendations": ["Follow up"], "messageIds": [self.public.pk], **changes}]}

    def run_job(self, job):
        run_quality_analysis({"job_id": job.pk}, self.worker_context)
        job.refresh_from_db()
        return job

    def test_real_agent_provider_and_common_masking_receive_only_public_history(self):
        job = self.job()
        invocation, pseudonymizer = _prepare(job)
        self.assertIsInstance(invocation.provider, DemoProvider)
        self.assertEqual(invocation.model, "demo")
        prompt = " ".join(row.content for row in invocation.messages)
        for private in ("customer@example.test", "+7 999 111-22-33", "Customer",
                        "Private consultation", "Secret transfer reason"):
            self.assertNotIn(private, prompt)
        self.assertIn("[[client_name]]", prompt)
        restored = validate_output(json.dumps(self.output(explanation="Helped [[client_name]]")), job, pseudonymizer)
        self.assertEqual(restored["conclusions"][0]["explanation"], "Helped Customer")

    def test_invalid_and_incomplete_output_never_validates(self):
        job = self.job()
        foreign = self.message(conversation=self.foreign_conversation)
        later = self.message(text="After completion")
        invalid = ["not json", "{}", '{"conclusions": [], "conclusions": []}',
                   json.dumps({"conclusions": []}), json.dumps({"conclusions": self.output()["conclusions"] * 2})]
        invalid += [json.dumps(self.output(**changes)) for changes in (
            {"code": "foreign"}, {"code": []}, {"value": True}, {"value": 9}, {"value": 1.0},
            {"messageIds": []}, {"messageIds": [foreign.pk]}, {"messageIds": [later.pk]},
            {"messageIds": [True]}, {"explanation": "  "}, {"recommendations": "advice"},
            {"recommendations": [""]}, {"explanation": "[[unknown]]"}, {"url": "https://foreign.test"},
        )]
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(InvalidQualityOutput):
                validate_output(text, job, Pseudonymizer())
        self.assertEqual(QualityResult.objects.count(), 0)

    def test_unit_worker_success_redelivery_preserves_original_and_explicit_repeat(self):
        job = self.job()
        reply = ChatResult(json.dumps(self.output()), "demo", 10, 4)
        with patch("chatballs.conversations.quality.worker.run_chat", return_value=reply) as provider_call:
            self.run_job(job)
            original = job.result.data
            self.run_job(job)
            self.assertEqual(provider_call.call_count, 1)
        self.assertEqual(job.state, "SUCCEEDED")
        self.assertEqual(job.result.data, original)
        self.assertEqual(original["temporalFacts"]["state"], "missing_history")
        repeat = self.job(completion_event_id=job.completion_event_id, completed_at=job.completed_at, repeat=True)
        self.assertEqual(repeat.revision, 2)
        self.assertEqual(QualityResult.objects.count(), 1)

    def test_actual_demo_non_json_reply_is_failed_instead_of_success(self):
        job = self.run_job(self.job())
        self.assertEqual((job.state, job.error_code), ("FAILED", "invalid_result"))
        self.assertFalse(hasattr(job, "result"))

    def test_missing_disabled_provider_and_runtime_failure_are_explicit(self):
        for changes in ({"provider_integration": None}, {"provider_integration": self.provider}):
            AIAgent.objects.filter(pk=self.agent.pk).update(**changes)
            if changes["provider_integration"]:
                Integration.objects.filter(pk=self.provider.pk).update(is_active=False)
            job = self.run_job(self.job())
            self.assertEqual((job.state, job.error_code), ("FAILED", "provider_unavailable"))
        Integration.objects.filter(pk=self.provider.pk).update(is_active=True)
        with patch("chatballs.conversations.quality.worker.run_chat",
                   side_effect=ProviderError("secret customer@example.test")):
            job = self.run_job(self.job())
        self.assertEqual(job.error_code, "provider_unavailable")
        self.assertEqual(list(LlmInvocation.objects.values_list("error", flat=True)), ["provider_unavailable"])

    def test_completion_captures_and_dispatches_via_real_outbox(self):
        event = record_fact(self.conversation, "CLOSED")
        job = QualityJob.objects.get(completion_event_id=event.operation_id)
        self.assertEqual(job.completed_at, event.occurred_at)
        outbox = OutboxEvent.objects.get(event_type=QUALITY_REQUESTED, aggregate_id=str(job.pk))
        dispatch(outbox)
        job.refresh_from_db()
        self.assertEqual(job.state, "FAILED")  # actual Demo response is not the quality contract
        dispatch(outbox)
        self.assertEqual(QualityJob.objects.count(), 1)
        self.assertEqual(LlmInvocation.objects.count(), 1)

    def test_normal_close_and_rollback_keep_snapshot_and_queue_atomic(self):
        Conversation.objects.filter(pk=self.conversation.pk).update(lifecycle="OPEN")
        with self.assertRaisesRegex(RuntimeError, "abort"), transaction.atomic():
            close_conversation(context=self.context, conversation_id=self.conversation.pk)
            raise RuntimeError("abort")
        self.assertEqual(QualityJob.objects.count(), 0)
        self.assertEqual(OutboxEvent.objects.filter(event_type=QUALITY_REQUESTED).count(), 0)
        operation = uuid4()
        for _ in range(2):
            close_conversation(context=self.context, conversation_id=self.conversation.pk, operation_id=operation)
        job = QualityJob.objects.get()
        self.assertEqual(job.completion_event_id, operation)
        self.assertEqual(OutboxEvent.objects.filter(event_type=QUALITY_REQUESTED).count(), 1)

    def test_enabled_inactivity_closure_schedules_the_same_worker_contract(self):
        Conversation.objects.filter(pk=self.conversation.pk).update(lifecycle="OPEN")
        self.conversation.refresh_from_db()
        self.assertTrue(close_inactive_locked(context=self.worker_context, conversation=self.conversation,
                                             cutoff=timezone.now() + timedelta(seconds=1)))
        job = QualityJob.objects.get()
        self.assertEqual(job.state, "WAITING")
        self.assertEqual(OutboxEvent.objects.filter(event_type=QUALITY_REQUESTED).count(), 1)

    def test_interrupted_delivery_finishes_without_second_model_call(self):
        from .jobs import start_quality_job

        job = self.job()
        start_quality_job(context=self.worker_context, job_id=job.pk)
        with self.assertRaisesRegex(RuntimeError, "quality_already_running"):
            self.run_job(job)
        QualityJob.objects.filter(pk=job.pk).update(started_at=timezone.now() - timedelta(seconds=301))
        self.run_job(job)
        self.assertEqual((job.state, job.error_code), ("FAILED", "analysis_interrupted"))
        self.assertEqual(LlmInvocation.objects.count(), 0)
