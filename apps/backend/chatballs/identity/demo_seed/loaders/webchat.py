"""Поля сайта и загруженные изображения из существующих данных веб-гостей."""

from io import BytesIO

from django.core.files.uploadedfile import UploadedFile

from chatballs.conversations.models import ContactFieldValue
from chatballs.identity.demo_seed import manifest
from chatballs.identity.demo_seed.refs import DemoRefs
from chatballs.tenancy.context import TenantContext
from chatballs.webchat.assets import upload_widget_asset


def load(context: TenantContext, refs: DemoRefs) -> None:
    data = manifest.load("conversations", refs.language)
    for item in data["conversations"]:
        if not item.get("webGuest") or not item.get("guestName"):
            continue
        conversation = refs.conversations[item["key"]]
        ContactFieldValue.objects.get_or_create(
            organization=refs.organization,
            contact=conversation.contact,
            integration=conversation.connection,
            key="name",
            defaults={"value": item["guestName"]},
        )
        avatar = item.get("guestAvatar")
        if avatar and not conversation.connection.widget_assets.exists():
            payload = manifest.media_bytes(f"avatars/{avatar}")
            upload_widget_asset(
                context=context,
                integration=conversation.connection,
                upload=UploadedFile(
                    file=BytesIO(payload), name=avatar, size=len(payload),
                ),
            )
            # Изображение доступно в хранилище, но не назначается кнопке или
            # шапке: оформление демо-виджета остаётся по дизайн-базлайну.
