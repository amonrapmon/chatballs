from django.test import TestCase

from chatballs.ai.assistance_behavior_base import AssistanceBehaviorData
from chatballs.ai.assistance_generation import begin
from chatballs.ai.models import Knowledge, KnowledgeFragment
from chatballs.ai.turn import plan_chat
from chatballs.support_portals.models import (
    PortalArticle,
    PortalArticleRevision,
    PortalCategory,
    SupportPortal,
)
from chatballs.tenancy.database import tenant_atomic


class AssistanceContextTests(AssistanceBehaviorData, TestCase):
    def test_draft_uses_answer_language_and_only_available_attached_sources(self):
        self.agent.answer_language = "en"
        self.agent.save()
        self.knowledge.is_enabled = False
        self.knowledge.save()
        unrelated = Knowledge.objects.create(
            organization=self.organization, category=self.knowledge.category,
            title="Unrelated source", content="Delivery uses a private unselected service.",
        )
        KnowledgeFragment.objects.create(organization=self.organization, knowledge=unrelated,
                                         chunk_index=0, content=unrelated.content)
        portal = SupportPortal.objects.create(
            organization=self.organization, name="Support", slug="assist-support",
            hosted_domain="assist-help.example.test",
        )
        category = PortalCategory.objects.create(portal=portal, slug="help", name="Help")
        article = PortalArticle.objects.create(portal=portal, category=category, slug="delivery")
        revision = PortalArticleRevision.objects.create(
            article=article, revision=1, title="Delivery article",
            content="Delivery is handled by a courier service.",
        )
        article.status = "PUBLISHED"
        article.published_revision = revision
        article.save()
        fragment = KnowledgeFragment.objects.create(
            organization=self.organization, portal_article=article,
            chunk_index=0, content=revision.content,
        )
        self.agent.portal_articles.add(article)
        with tenant_atomic(self.worker_context):
            suggestion, conversation, history, _, mask, _ = begin(
                self.worker_context, self.request().public_id,
            )
            plan = plan_chat(agent=suggestion.attempt.agent, message="delivery", history=history,
                             conversation=conversation, pseudonymizer=mask, style_guard=False)
            self.assertEqual(plan.fragment_ids, [fragment.pk])
            prompt = str(plan.job.messages)
            self.assertIn("English", prompt)
            self.assertIn("Delivery article", prompt)
            self.assertNotIn("Unrelated source", prompt)
            self.assertNotIn("help@example.test", prompt)
            article.status = "DRAFT"
            article.save()
            plan = plan_chat(agent=suggestion.attempt.agent, message="delivery", history=history,
                             conversation=conversation, pseudonymizer=mask, style_guard=False)
            self.assertEqual(plan.fragment_ids, [])
            self.assertNotIn("Delivery article", str(plan.job.messages))
