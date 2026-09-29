"""Иконки кнопки и шапки виджета (SPEC-0021 R-3, R-4).

Принимаются SVG и PNG до 256 КБ; PNG — не меньше 96×96, чтобы кнопка не
расплывалась на экранах с высокой плотностью. SVG очищается до сохранения.
Тип определяется по содержимому, а не по имени файла и заявленному типу.
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.urls import reverse

from chatballs.i18n import t
from chatballs.identity.logo_svg import SVG_CONTENT_TYPE, looks_like_svg
from chatballs.integrations.models import Integration
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic
from chatballs.tenancy.storage import adjust_storage_usage
from chatballs.tenancy.storage_quota import finalize_storage, release_storage, reserve_storage
from chatballs.webchat.models import WidgetAsset
from chatballs.webchat.svg_sanitizer import UnsafeSvg, sanitize_svg

MAX_ASSET_BYTES = 256 * 1024
MIN_PNG_SIDE = 96
PNG_CONTENT_TYPE = "image/png"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_size(data: bytes) -> tuple[int, int] | None:
    """Ширина и высота из заголовка IHDR — первого блока любого PNG."""

    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _asset_content(data: bytes) -> tuple[bytes, str, str]:
    if data.startswith(_PNG_SIGNATURE):
        size = _png_size(data)
        if size is None:
            raise ValidationError({"file": t("webchat.asset_formats")})
        if min(size) < MIN_PNG_SIDE:
            raise ValidationError({"file": t("webchat.asset_png_too_small")})
        return data, PNG_CONTENT_TYPE, ".png"
    if looks_like_svg(data):
        try:
            return sanitize_svg(data), SVG_CONTENT_TYPE, ".svg"
        except UnsafeSvg as error:
            raise ValidationError({"file": t("webchat.asset_svg_unreadable")}) from error
    raise ValidationError({"file": t("webchat.asset_formats")})


def _read(upload: UploadedFile) -> bytes:
    if upload.size is not None and upload.size > MAX_ASSET_BYTES:
        raise ValidationError({"file": t("webchat.asset_too_large")})
    data = upload.read(MAX_ASSET_BYTES + 1)
    if not data:
        raise ValidationError({"file": t("webchat.asset_choose_file")})
    if len(data) > MAX_ASSET_BYTES:
        raise ValidationError({"file": t("webchat.asset_too_large")})
    return data


@transaction.atomic
def upload_widget_asset(
    *,
    context: TenantContext,
    integration: Integration,
    upload: UploadedFile,
    uploaded_by=None,
) -> WidgetAsset:
    content, content_type, suffix = _asset_content(_read(upload))
    asset = WidgetAsset(
        organization_id=context.organization_id,
        integration=integration,
        content_type=content_type,
        size=len(content),
        uploaded_by=uploaded_by,
    )
    reservation_key = f"widget-asset:{uuid.uuid4()}"
    reserve_storage(context=context, expected_bytes=len(content), idempotency_key=reservation_key)
    try:
        asset.file.save(suffix, ContentFile(content), save=False)
        asset.save()
    except Exception:
        release_storage(context=context, idempotency_key=reservation_key)
        raise
    finalize_storage(context=context, idempotency_key=reservation_key, actual_bytes=len(content))
    return asset


def widget_asset_url(asset: WidgetAsset) -> str:
    """Адрес от корня установки: лоадер дописывает к нему свой origin."""

    return reverse("webchat-asset", kwargs={"public_id": asset.public_id})


def widget_asset_files(integration: Integration) -> list[tuple[str, int]]:
    """Файлы иконок интеграции: строки уходят с ней каскадом, файлы — нет."""

    return list(integration.widget_assets.values_list("file", "size"))


def discard_widget_asset_files(*, context: TenantContext, files: list[tuple[str, int]]) -> None:
    """Освобождает место сразу, а файлы стирает после коммита удаления."""

    if not files:
        return
    adjust_storage_usage(context=context, delta_bytes=-sum(size for _name, size in files))
    storage = WidgetAsset._meta.get_field("file").storage
    organization_id = context.organization_id

    def delete_files() -> None:
        # Ограждение хранилища требует контекст организации, а после коммита
        # транзакции с SET LOCAL его уже нет.
        with tenant_atomic(organization_id):
            for name, _size in files:
                storage.delete(name)

    transaction.on_commit(delete_files)
