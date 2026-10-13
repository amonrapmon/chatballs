from unittest import mock

from chatballs.conversations import transports
from chatballs.conversations.email_workflow_test_base import EmailWorkflowTestBase
from chatballs.conversations.inbound_media import _store_attachment, _store_voice
from chatballs.conversations.models import Message, MessageKind
from chatballs.conversations.transports.base import InboundFile, InboundMessage


class InboundMediaErrorTests(EmailWorkflowTestBase):
    def test_download_failure_preserves_message_in_customer_language(self):
        inbound = InboundMessage(external_id="voice", user_id="visitor", chat_id="visitor", text="", display_name="")
        for language, file_text, voice_text in (
            ("ru", "Файл «report.pdf» (не удалось загрузить)", "Голосовое сообщение (не удалось загрузить)"),
            ("en", "File “report.pdf” (download failed)", "Voice message (download failed)"),
        ):
            with self.subTest(language=language):
                self.organization.language = language
                self.organization.save()
                self.mailbox.refresh_from_db()
                attachment = Message.objects.create(conversation=self.conversation, author_type="CONTACT", kind="file")
                voice = Message.objects.create(conversation=self.conversation, author_type="CONTACT", kind="voice")
                with mock.patch.object(transports, "download_file", side_effect=OSError("network unavailable")):
                    _store_attachment(self.mailbox, InboundFile(name="report.pdf"), attachment)
                with mock.patch.object(transports, "download_voice", side_effect=OSError("network unavailable")):
                    _store_voice(self.mailbox, inbound, voice)
                attachment.refresh_from_db()
                voice.refresh_from_db()
                self.assertEqual((attachment.kind, attachment.text), (MessageKind.TEXT, file_text))
                self.assertEqual((voice.kind, voice.text), (MessageKind.TEXT, voice_text))
