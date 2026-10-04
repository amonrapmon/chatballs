"""Настройки формы: PATCH, версия согласия, удаление схемы и публичная выдача."""

from django.test import TestCase
from rest_framework.test import APIClient

from chatballs.channels.models import Channel
from chatballs.identity.models import HumanUser, Organization, OrganizationMembership
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.serializers import integration_payload
from chatballs.integrations.services import IntegrationInput, create_integration, update_integration
from chatballs.testing import TenantAPIClient, system_tenant_context
from chatballs.webchat.testing import create_web_widget

CUSTOM = {"key": "order_id", "label": "Номер заказа", "type": "string"}
FORM = {
    "enabled": True,
    "title": "Представьтесь",
    "fields": [{"key": "name", "required": True}, {"key": "order_id", "required": False}],
}
UNSAFE_CONSENT = (
    'Принимаю <a href="https://example.ru/privacy" onclick="alert(1)">политику</a>.<br>'
    '<strong onmouseover="alert(1)">Чат записывается.</strong><script>alert(1)</script>'
    '<a href="javascript:alert(1)">ссылка</a><h1>Итог</h1>'
)
SAFE_CONSENT = (
    'Принимаю <a href="https://example.ru/privacy" target="_blank" rel="noopener noreferrer nofollow">политику</a>.<br>'
    "<strong>Чат записывается.</strong>"
    '<a target="_blank" rel="noopener noreferrer nofollow">ссылка</a>Итог'
)


class PreChatConfigTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Form", slug="pre-chat")
        self.channel = Channel.objects.create(organization=self.organization, code="form", name="Form")
        self.context = system_tenant_context(self.organization)
        self.integration = create_integration(
            context=self.context,
            data=IntegrationInput(
                provider=IntegrationProvider.WEB, name="Site", channel_id=self.channel.id,
                config={"allowedOrigins": ["form.example.test"]},
            ),
        )
        user = HumanUser.objects.create_user(email="form@example.test")
        OrganizationMembership.objects.create(user=user, organization=self.organization, role="ADMIN")
        self.client = TenantAPIClient()
        self.client.force_authenticate(user=user)

    def _patch(self, **config):
        return self.client.patch(
            f"/api/v1/integrations/{self.integration.id}/",
            {"config": {"allowedOrigins": ["form.example.test"], **config}}, format="json"
        )

    def _config(self, **config):
        response = self._patch(**config)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["integration"]["config"]

    def _public(self):
        return APIClient().get(
            "/api/v1/webchat/config/", {"widgetKey": self.integration.web_chat_widget.public_key},
            HTTP_ORIGIN="https://form.example.test",
        ).json()

    def test_default_is_disabled_for_new_and_legacy_widgets(self):
        default = {"enabled": False, "title": "", "fields": []}
        self.assertEqual(integration_payload(self.integration)["config"]["preChat"], default)
        self.assertEqual(self._public()["preChat"], default)
        legacy = create_web_widget(self.channel, name="Legacy")
        self.assertEqual(integration_payload(legacy.integration)["config"]["preChat"], default)
        public = APIClient().get("/api/v1/webchat/config/", {"widgetKey": legacy.public_key}).json()
        self.assertEqual(public["preChat"], default)

    def test_valid_form_is_saved_and_published_with_field_schema(self):
        form = {**FORM, "fields": [*FORM["fields"], {"key": "email", "required": True}, {"key": "phone", "required": False}]}
        config = self._config(fields=[CUSTOM], preChat=form)
        self.assertEqual(config["preChat"], form)
        self.integration.refresh_from_db()
        self.assertEqual(self.integration.config["preChat"], form)
        public = self._public()
        self.assertEqual(public["preChat"], form)
        self.assertEqual(public["fields"][0]["key"], "order_id")
        self.assertNotIn("aiAccess", public["fields"][0])
        self.assertNotIn("aiVisible", public["fields"][0])
        self.assertEqual(self.integration.web_chat_widget.presentation_config["preChat"], form)
        self.assertEqual(self._config(title="New title")["preChat"], form)

    def test_invalid_form_is_rejected_without_saving(self):
        self._config(fields=[CUSTOM], preChat=FORM)
        invalid = [
            None, [], {"enabled": "true"}, {"enabled": 1}, {"title": 42},
            {"fields": {}}, {"fields": [None]}, {"fields": [{"key": []}]},
            {"fields": [{"key": "missing", "required": False}]},
            {"fields": [{"key": "name", "required": "false"}]},
            {"fields": [{"key": "name"}, {"key": "name"}]},
        ]
        for form in invalid:
            with self.subTest(form=form):
                self.assertEqual(self._patch(preChat=form).status_code, 400)
                self.integration.refresh_from_db()
                self.assertEqual(self.integration.config["preChat"], FORM)

    def test_custom_field_from_another_connection_is_rejected(self):
        create_integration(
            context=self.context,
            data=IntegrationInput(provider=IntegrationProvider.WEB, name="Other", channel_id=self.channel.id, config={"fields": [CUSTOM]}),
        )
        self.assertEqual(self._patch(preChat=FORM).status_code, 400)

    def test_schema_deletion_removes_custom_fields_from_form(self):
        expected = {**FORM, "fields": [{"key": "name", "required": True}]}
        for full_config in (False, True):
            with self.subTest(full_config=full_config):
                self._config(fields=[CUSTOM], preChat=FORM)
                config = self._config(fields=[], **({"preChat": FORM} if full_config else {}))
                self.assertEqual(config["preChat"], expected)
                self.assertEqual(self._public()["preChat"], expected)
                self.assertEqual(self._public()["fields"], [])
        # Явная ссылка на уже удалённое поле отклоняется.
        self.assertEqual(self._patch(preChat=FORM).status_code, 400)

    def test_consent_version_is_owned_by_server_and_changes_only_with_text(self):
        initial = integration_payload(self.integration)["config"]["consentVersion"]
        self.assertEqual(initial, "v1")
        changed = self._config(consentText="Согласие", consentVersion="v900")
        self.assertEqual(changed["consentVersion"], "v2")
        unchanged = self._config(consentText=" Согласие ", consentVersion="v1")
        self.assertEqual(unchanged["consentVersion"], "v2")
        omitted = self._config(preChat={"enabled": False})
        self.assertEqual((omitted["consentText"], omitted["consentVersion"]), ("Согласие", "v2"))
        changed = self._config(consentText="Новое согласие")
        self.assertEqual(changed["consentVersion"], "v3")
        self.assertEqual(self._public()["consent"], {"text": "Новое согласие", "version": "v3"})
        self.assertEqual(self._config(consentText="")["consentVersion"], "v4")

    def test_consent_html_is_sanitized_on_save(self):
        saved = self._config(consentText=UNSAFE_CONSENT)
        self.assertEqual(saved["consentText"], SAFE_CONSENT)
        self.integration.refresh_from_db()
        self.assertEqual(self.integration.config["consent_text"], SAFE_CONSENT)
        self.assertEqual(self.integration.web_chat_widget.consent_config["consent_text"], SAFE_CONSENT)
        self.assertEqual(self._public()["consent"], {"text": SAFE_CONSENT, "version": "v2"})

    def test_consent_version_follows_sanitized_text(self):
        self.assertEqual(self._config(consentText=UNSAFE_CONSENT)["consentVersion"], "v2")
        # Отличается только вырезаемое — очищенный текст тот же, версия прежняя.
        for text in (SAFE_CONSENT, UNSAFE_CONSENT.replace("alert(1)", "alert(2)"), f"{SAFE_CONSENT}<style>a{{}}</style>"):
            with self.subTest(text=text):
                self.assertEqual(self._config(consentText=text)["consentVersion"], "v2")
        self.assertEqual(self._config(consentText=f"{SAFE_CONSENT}<u>!</u>")["consentVersion"], "v3")

    def test_consent_saved_before_sanitizing_is_published_clean(self):
        self.integration.config = {**self.integration.config, "consent_text": UNSAFE_CONSENT, "consent_version": "v5"}
        self.integration.save(update_fields=["config"])
        widget = self.integration.web_chat_widget
        widget.consent_config = {"consent_text": UNSAFE_CONSENT, "consent_version": "v5"}
        widget.save(update_fields=["consent_config"])
        self.assertEqual(self._public()["consent"], {"text": SAFE_CONSENT, "version": "v5"})
        self.assertEqual(integration_payload(self.integration)["config"]["consentText"], SAFE_CONSENT)
        # Пересохранение того же текста версию не повышает: сравнение идёт по очищенному.
        for text in (UNSAFE_CONSENT, SAFE_CONSENT):
            with self.subTest(text=text):
                self.assertEqual(self._config(consentText=text)["consentVersion"], "v5")
        self.integration.refresh_from_db()
        self.assertEqual(self.integration.config["consent_text"], SAFE_CONSENT)

    def test_legacy_consent_version_is_preserved_until_text_changes(self):
        self.integration.config = {}
        self.integration.save(update_fields=["config"])
        self.assertEqual(self._config(consentText="First legacy text")["consentVersion"], "v2")
        self.integration.config = {"consent_text": "Legacy", "consent_version": "release"}
        self.integration.save(update_fields=["config"])
        self.assertEqual(self._config(consentText="Legacy", consentVersion="v1")["consentVersion"], "release")
        self.assertEqual(self._config(consentText="Changed")["consentVersion"], "release.1")
        self.assertEqual(self._config(consentText="Again")["consentVersion"], "release.2")

    def test_stale_service_object_does_not_reuse_consent_version(self):
        for text, version in (("First", "v2"), ("Second", "v3")):
            saved = update_integration(
                context=self.context, integration=self.integration,
                data=IntegrationInput(provider="WEB", name="Site", channel_id=self.channel.id, config={"consentText": text}),
            )
            self.assertEqual(saved.config["consent_version"], version)
