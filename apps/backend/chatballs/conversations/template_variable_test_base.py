"""Variable acceptance setup, exclusively in the isolated Django test database."""

from django.db.models import JSONField, Value

from chatballs.channels.models import Channel
from chatballs.conversations.models import Contact, ContactFieldValue, Conversation
from chatballs.conversations.template_test_base import TemplateTestBase
from chatballs.conversations.template_variables import field_key
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider


class VariableTestBase(TemplateTestBase):
    def setUp(self):
        super().setUp()
        self.employee.user.full_name = "Operator"
        self.employee.user.save(update_fields=["full_name"])
        self.connection, self.dialog = self.web_dialog(self.organization, "Visible")
        self.key = field_key(self.connection.pk, "status")
        self.contact = self.dialog.contact
        self.contact.email = "current@client.test"
        self.contact.phone = "+79991234567"
        self.contact.company = "Client company"
        self.contact.city = "City"
        self.contact.description = "Description"
        self.contact.save()

    def web_dialog(self, organization, name, group=None):
        channel = Channel.objects.create(organization=organization, code=name, name=name)
        connection = Integration.objects.create(
            organization=organization, channel=channel, name=name,
            kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.WEB,
            config={"fields": [
                {"key": "status", "label": "Status", "type": "enum", "order": 0,
                 "options": [{"value": "ready", "label": "Ready"}]},
                {"key": "enabled", "label": "Enabled", "type": "boolean", "order": 1},
                {"key": "count", "label": "Count", "type": "number", "order": 2},
            ]},
        )
        dialog = Conversation.objects.create(
            organization=organization, channel=channel, connection=connection, group=group,
            contact=Contact.objects.create(organization=organization, name=name),
        )
        return connection, dialog

    def value(self, key, value, dialog=None):
        dialog = dialog or self.dialog
        ContactFieldValue.objects.update_or_create(
            organization=dialog.organization, contact=dialog.contact,
            integration=dialog.connection, key=key,
            defaults={"value": Value(None, output_field=JSONField()) if value is None else value},
        )

    def template(self, text, client=None, title="Greeting"):
        response = self.create(client=client, text=text, title=title)
        self.assertEqual(response.status_code, 201, response.data)
        return response.json()["template"]["id"]

    def render(self, template_id, dialog=None, client=None, **extra):
        return (client or self.client).post(
            f"{self.base}{template_id}/render/",
            {"conversationId": (dialog or self.dialog).pk, **extra}, format="json",
        )

    def catalog(self, dialog=None, client=None, **params):
        if dialog is not None:
            params["conversationId"] = dialog.pk
        return (client or self.client).get(self.base + "variables/", params)
