"""Reuse chat upload policy and keep file identity stable across mail retries."""

import hashlib

from django.core.files.base import ContentFile
from rest_framework.exceptions import ValidationError

from chatballs.conversations.attachment_policy import validate_upload
from chatballs.conversations.transports.base import guess_content_type, safe_filename


def read_attachment(upload):
    if upload is None:
        return None
    problem = validate_upload(upload)
    if problem:
        raise ValidationError({"detail": problem})
    name = safe_filename(upload.name or "")
    content_type = (upload.content_type or "").split(";")[0] or guess_content_type(name)
    return upload.read(), name, content_type


def attachment_matches(message, attachment):
    if not message.attachment:
        return attachment is None
    if attachment is None:
        return False
    content, name, content_type = attachment
    if (message.attachment_name, message.attachment_content_type, message.attachment_size) != (
        name, content_type, len(content),
    ):
        return False
    with message.attachment.open("rb") as stored:
        digest = hashlib.file_digest(stored, "sha256").digest()
    return digest == hashlib.sha256(content).digest()


def store_attachment(message, attachment):
    if attachment is None:
        return
    content, name, content_type = attachment
    message.kind = "file"
    message.attachment_name, message.attachment_content_type = name, content_type
    message.attachment_size = len(content)
    message.attachment.save(name, ContentFile(content), save=False)
    message.save(update_fields=["kind", "attachment", "attachment_name", "attachment_content_type", "attachment_size"])
