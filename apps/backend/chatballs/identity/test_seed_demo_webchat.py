"""Новые модели веб-чата в демонаборе: реестр, повторный запуск и удаление."""

from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings

from chatballs.conversations.models import ContactFieldValue
from chatballs.identity.demo_models import DemoDataset, DemoDatasetStatus
from chatballs.identity.demo_seed import manifest, service
from chatballs.identity.demo_seed.loaders import webchat
from chatballs.identity.demo_seed.refs import DemoRefs
from chatballs.identity.demo_seed.registry import _delete_record
from chatballs.identity.setup import SetupInput, complete_setup
from chatballs.identity.test_seed_demo import OWNER
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic
from chatballs.tenancy.models import OrganizationStorageUsage
from chatballs.webchat.appearance import DEFAULTS
from chatballs.webchat.models import WidgetAsset


class DemoWebChatTests(TestCase):
    def setUp(self) -> None:
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        result = complete_setup(SetupInput(**OWNER))
        self.context = TenantContext.for_resource(result.organization)
        with tenant_atomic(self.context):
            self.dataset = DemoDataset.objects.create(
                organization=result.organization, status=DemoDatasetStatus.INSTALLING,
            )
            self.dataset = service.install(context=self.context, dataset=self.dataset)
        self.assertEqual(self.dataset.status, DemoDatasetStatus.INSTALLED, self.dataset.error)

    def test_web_guest_data_is_registered_without_changing_widget_appearance(self) -> None:
        field = ContactFieldValue.objects.get(key="name")
        self.assertEqual(field.value, field.contact.name)
        asset = WidgetAsset.objects.get(integration=field.integration)
        with tenant_atomic(self.context):
            self.assertTrue(asset.file.storage.exists(asset.file.name))
        for instance in (field, asset):
            self.assertTrue(self.dataset.records.filter(
                content_type__model=instance._meta.model_name,
                object_id=str(instance.pk),
            ).exists())
        self.assertEqual(field.integration.config["appearance"], DEFAULTS)
        # Ключ диалога берётся из манифеста, как при штатной установке.
        item = next(
            item for item in manifest.load("conversations")["conversations"]
            if item.get("guestName") == field.value
        )
        refs = DemoRefs(
            organization=self.context.organization,
            conversations={item["key"]: field.contact.conversations.get()},
        )
        with tenant_atomic(self.context):
            webchat.load(self.context, refs)
        self.assertEqual(ContactFieldValue.objects.count(), 1)
        self.assertEqual(WidgetAsset.objects.count(), 1)

    def test_asset_removal_deletes_file_and_releases_its_storage_usage(self) -> None:
        asset = WidgetAsset.objects.get()
        path, storage, size = asset.file.name, asset.file.storage, asset.size
        before = OrganizationStorageUsage.objects.get(organization=self.context.organization).bytes_used
        record = self.dataset.records.get(content_type__model="widgetasset", object_id=str(asset.pk))
        with self.captureOnCommitCallbacks(execute=True), tenant_atomic(self.context):
            self.assertTrue(_delete_record(record, set()))
        with tenant_atomic(self.context):
            self.assertFalse(storage.exists(path))
        self.assertFalse(WidgetAsset.objects.exists())
        after = OrganizationStorageUsage.objects.get(organization=self.context.organization).bytes_used
        self.assertEqual(after, before - size)
