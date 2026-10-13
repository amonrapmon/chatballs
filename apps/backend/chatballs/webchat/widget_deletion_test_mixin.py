"""Widget reset after deletion by the test organization owner."""

import json

from chatballs.webchat.testing import create_web_widget


class WidgetDeletionTestMixin:
    def test_deleted_conversation_resets_widget_thread(self) -> None:
        # Диалог удалили в рабочем месте: виджет должен начать с чистого листа,
        # а не показывать клиенту переписку, которой больше нет.
        from chatballs.conversations.models import Conversation
        from chatballs.conversations.services import delete_conversation
        from chatballs.identity.models import EmployeeRole, OrganizationMembership
        from chatballs.tenancy.context import TenantContext

        widget = create_web_widget(self.channel, name="Виджет")
        token = self._session(widget.public_key).json()["token"]
        self.client.post(
            "/api/v1/webchat/messages/",
            data=json.dumps({"text": "Здравствуйте"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token}"},
        )
        payload = self.client.get(
            "/api/v1/webchat/messages/?since=0",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        self.assertFalse(payload["reset"])
        last_id = max(message["id"] for message in payload["messages"])

        conversation = Conversation.objects.get(channel=self.channel)
        delete_conversation(
            context=TenantContext.for_membership(OrganizationMembership.objects.get(
                organization=self.organization, role=EmployeeRole.OWNER,
            )),
            conversation=conversation,
        )

        after = self.client.get(
            f"/api/v1/webchat/messages/?since={last_id}",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        self.assertTrue(after["reset"])
        self.assertEqual(after["messages"], [])
