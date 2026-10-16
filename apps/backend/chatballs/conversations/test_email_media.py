from unittest import mock

from chatballs.conversations.test_attachments import AttachmentTestCase
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider


class EmailAttachmentTests(AttachmentTestCase):
    def test_email_send_file_adds_mime_attachment(self) -> None:
        from chatballs.conversations.transports import email as email_transport

        integration = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.EMAIL,
            name="Почта",
            secret="pass",
            channel=self.channel,
            config={"email": "support@example.com", "smtp_host": "smtp.example.com", "smtp_ssl": True},
        )
        sent: list = []

        class FakeSMTP:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def quit(self):
                pass

            def login(self, *args):
                pass

            def send_message(self, message):
                sent.append(message)

        with mock.patch("chatballs.conversations.transports.email_smtp.smtplib.SMTP_SSL", FakeSMTP):
            self.assertTrue(email_transport.send_file(integration, chat_id="client@example.com", user_id="", content=b"%PDF", filename="смета.pdf", content_type="application/pdf"))
        attachments = list(sent[0].iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_filename(), "смета.pdf")
        self.assertEqual(attachments[0].get_content(), b"%PDF")
