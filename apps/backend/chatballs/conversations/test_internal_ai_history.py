"""Internal records never consume the model's history window."""

from chatballs.ai.models import AIAgent
from chatballs.ai.runtime import build_turn_messages
from chatballs.ai.turn import turn_pseudonymizer
from chatballs.conversations.ai_history import conversation_history
from chatballs.conversations.audience import ConversationAudience
from chatballs.conversations.comment_test_base import CommentTestBase
from chatballs.conversations.history_selectors import (
    conversation_records,
    customer_visible_messages,
)
from chatballs.conversations.models import Message, MessageAuthor
from chatballs.conversations.system_events import OPERATOR_ONLY_EVENTS


class InternalAIHistoryTests(CommentTestBase):
    def message(self, text, **changes):
        return Message.objects.create(**{
            "conversation": self.conversation, "author_type": MessageAuthor.CONTACT,
            "text": text, **changes,
        })

    def test_exclusion_before_limit_preserves_public_history_and_current_question(self):
        self.message("Older question")
        self.message("Public answer", author_type=MessageAuthor.AI)
        for index in range(8):
            self.comment(text=f"Internal secret {index}")
            self.message("Hidden event", system_event=OPERATOR_ONLY_EVENTS[index % 2])
        self.message("Current question")
        self.comment(text="Newest private note")
        self.message("Newest hidden event", system_event=OPERATOR_ONLY_EVENTS[0])
        expected = [
            {"role": "user", "content": "Older question"},
            {"role": "assistant", "content": "Public answer"},
        ]
        self.assertEqual(conversation_history(self.conversation, 2), expected)
        self.assertEqual(conversation_history(self.conversation, 1), expected[-1:])
        self.assertEqual(conversation_history(self.conversation, 0), [])
        agent = AIAgent.objects.create(channel=self.conversation.channel, name="Agent")
        masker = turn_pseudonymizer(self.conversation)
        prompt = build_turn_messages(
            agent=agent, message="Current question",
            history=conversation_history(self.conversation, 2), fragments=[],
            conversation=self.conversation, pseudonymizer=masker,
        )
        outgoing = "\n".join(masker.mask(item.content) for item in prompt)
        self.assertIn("Public answer", outgoing)
        self.assertNotIn("Internal secret", outgoing)
        self.assertNotIn("private note", outgoing)
        self.assertNotIn("hidden event", outgoing.lower())

    def test_internal_queryset_cannot_be_used_as_customer_context(self):
        self.comment()
        internal = conversation_records(self.conversation, audience=ConversationAudience.INTERNAL)
        with self.assertRaises(ValueError):
            customer_visible_messages(internal)

    def test_comment_only_conversation_has_no_ai_history(self):
        self.comment()
        self.assertEqual(conversation_history(self.conversation, 20), [])
