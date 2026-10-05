from chatballs.conversations.models import ContactFieldValue
from chatballs.conversations.test_chat_extras import ChatExtrasTestCase
from chatballs.webchat.testing import create_web_widget


class SiteFieldManualEditTests(ChatExtrasTestCase):
    def test_dialog_edit_clears_site_provenance_even_if_value_is_same(self) -> None:
        widget = create_web_widget(self.channel)
        contact = self.conversation.contact
        ContactFieldValue.objects.create(
            organization=self.organization, contact=contact, integration=widget.integration,
            key="name", value=contact.name,
        )
        response = self.client.post(
            f"/api/v1/conversations/{self.conversation.id}/contact/",
            {"name": contact.name}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(ContactFieldValue.objects.filter(contact=contact, key="name").exists())

    def test_client_edit_clears_site_provenance(self) -> None:
        widget = create_web_widget(self.channel)
        contact = self.conversation.contact
        ContactFieldValue.objects.create(
            organization=self.organization, contact=contact, integration=widget.integration,
            key="phone", value="+79991234567",
        )
        response = self.admin_client.patch(
            f"/api/v1/conversations/clients/{contact.id}/",
            {"phone": "+79991234567"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(ContactFieldValue.objects.filter(contact=contact, key="phone").exists())
