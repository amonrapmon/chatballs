"""Assistance checks use the project's DEMO provider and isolated test database."""

from django.test import override_settings

from chatballs.ai.assistance_services import request_suggestion
from chatballs.ai.assistance_test_base import AssistanceTestData
from chatballs.ai.models import Knowledge, KnowledgeCategory, KnowledgeFragment
from chatballs.conversations.models import Message
from chatballs.integrations.models import (
    Integration,
    IntegrationKind,
    IntegrationProvider,
)
from chatballs.tenancy.context import TenantContext


class AssistanceBehaviorData(AssistanceTestData):
    def setUp(self):
        self.enterContext(override_settings(CHATBALLS_AI_PROVIDER=""))
        super().setUp()
        self.context = TenantContext.for_membership(self.member)
        self.worker_context = TenantContext.for_resource(self.organization)
        integration = Integration.objects.create(
            organization=self.organization, name="Demo", kind=IntegrationKind.LLM_PROVIDER,
            provider=IntegrationProvider.DEMO, secret="demo", config={"default_model": "demo"},
        )
        self.agent.provider_integration = integration
        self.agent.assistance_enabled = True
        self.agent.instructions = "Answer delivery questions from the attached knowledge."
        self.agent.save()
        category = KnowledgeCategory.objects.create(organization=self.organization, name="Help")
        self.knowledge = Knowledge.objects.create(
            organization=self.organization, category=category, title="Delivery",
            content="Delivery is by courier. Contact support at help@example.test for delivery.",
        )
        KnowledgeFragment.objects.create(
            organization=self.organization, knowledge=self.knowledge, chunk_index=0,
            content=self.knowledge.content,
        )
        self.agent.knowledge_items.add(self.knowledge)
        self.incoming = Message.objects.create(
            conversation=self.conversation, author_type="CONTACT", text="How is delivery handled?",
        )

    def request(self, key="initial", attempt_id=None):
        return request_suggestion(context=self.context, conversation_id=self.conversation.pk,
                                  key=key, attempt_id=attempt_id)

    def generate(self, suggestion):
        from chatballs.ai.assistance_generation import run_requested_assistance

        run_requested_assistance({"suggestionId": str(suggestion.public_id)}, self.worker_context)
        suggestion.refresh_from_db()
        return suggestion
