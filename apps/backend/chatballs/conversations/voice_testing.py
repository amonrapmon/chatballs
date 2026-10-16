
from django.core.files.base import ContentFile
from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations.models import (
    Contact,
    Conversation,
    Message,
    MessageAuthor,
    MessageKind,
)
from chatballs.conversations.transports.base import InboundMessage
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import (
    Organization,
)
from chatballs.integrations.models import (
    Integration,
    IntegrationKind,
    IntegrationProvider,
)
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import TenantAPIClient as APIClient


class VoiceFixtureMixin:
    """Голосовые сообщения (дизайн-базлайн v2, кадр H): приём, отдача,
    расшифровка через BYOK, отправка оператором в Telegram и MAX."""

    def setUp(self) -> None:
        bootstrap_owner(email="owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.channel = Channel.objects.create(
            organization=self.organization, code="line", name="Линия"
        )
        self.integration = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.TELEGRAM,
            name="Bot",
            secret="token",
            channel=self.channel,
        )
        self.client = APIClient()
        self.client.login(username="owner@example.com", password="temporary-password")

    def _voice_inbound(self, external_id: str = "v-1") -> InboundMessage:
        return InboundMessage(
            external_id=external_id,
            user_id="u-1",
            chat_id="c-1",
            text="",
            display_name="Ольга",
            voice_file_id="file-123",
            voice_duration=14,
            voice_mime="audio/ogg",
        )

    def _voice_message(self) -> Message:
        contact = Contact.objects.create(organization=self.organization, name="Ольга")
        conversation = Conversation.objects.create(
            organization=self.organization,
            channel=self.channel,
            connection=self.integration,
            contact=contact,
        )
        message = Message.objects.create(
            conversation=conversation,
            author_type=MessageAuthor.CONTACT,
            kind=MessageKind.VOICE,
            audio_content_type="audio/ogg",
            duration_seconds=14,
        )
        with tenant_atomic(self.organization.id):
            message.audio.save("voice.ogg", ContentFile(b"OGGDATA"), save=False)
        message.save(update_fields=["audio"])
        return message


class VoiceTestCase(VoiceFixtureMixin, TestCase):
    pass


