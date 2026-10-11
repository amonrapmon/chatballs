"""Organization-scoped media paths; models.py reexports historical migration names."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chatballs.conversations.contact_models import Contact
    from chatballs.conversations.message_models import Message


def contact_avatar_upload_path(instance: "Contact", filename: str) -> str:
    import uuid
    from pathlib import Path

    suffix = Path(filename).suffix.lower()[:8] or ".jpg"
    return f"organizations/{instance.organization.public_id}/contacts/{uuid.uuid4().hex}{suffix}"


def message_audio_upload_path(instance: "Message", filename: str) -> str:
    import uuid
    from pathlib import Path

    suffix = Path(filename).suffix.lower() or ".ogg"
    organization = instance.conversation.organization
    return f"organizations/{organization.public_id}/voice/{uuid.uuid4().hex}{suffix}"


def message_attachment_upload_path(instance: "Message", filename: str) -> str:
    import uuid
    from pathlib import Path

    suffix = Path(filename).suffix.lower()[:16]
    organization = instance.conversation.organization
    return f"organizations/{organization.public_id}/files/{uuid.uuid4().hex}{suffix}"
