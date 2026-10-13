"""Shared upload limits for public messages and mail continuation."""

from chatballs.conversations.transports.base import safe_filename
from chatballs.i18n import t

MAX_FILE_BYTES = 20 * 1024 * 1024
BLOCKED_SUFFIXES = (".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".ps1", ".vbs", ".js", ".jar", ".sh", ".dll")


def validate_upload(upload) -> str:
    if upload.size > MAX_FILE_BYTES:
        return t("conversations.attachment_too_large")
    if not upload.size:
        return t("conversations.attachment_empty")
    if safe_filename(upload.name or "").lower().endswith(BLOCKED_SUFFIXES):
        return t("conversations.attachment_type_blocked")
    return ""
