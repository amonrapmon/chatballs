"""Shared, provider-neutral binary checks for Connector ingress and outbound.

The Connector uses native Message.audio / Message.attachment storage. Adapters
provide bytes and honest manifests, never provider URLs. Known browser-playable
formats get signature checks; other documents inherit the native suffix policy.
"""
from __future__ import annotations

import hashlib
import mimetypes
import re

from chatballs.conversations.attachment_policy import BLOCKED_SUFFIXES, MAX_FILE_BYTES
from chatballs.conversations.transports.base import safe_filename

MAX_VOICE_BYTES = 10 * 1024 * 1024
VOICE_MIMES = frozenset({
    "audio/ogg", "audio/webm", "audio/mpeg", "audio/mp4", "audio/wav",
})
IMAGE_MIMES = frozenset({
    "image/jpeg", "image/png", "image/gif", "image/webp",
})
VIDEO_MIMES = frozenset({"video/mp4", "video/webm"})
MEDIA_MIMES = VOICE_MIMES | IMAGE_MIMES | VIDEO_MIMES
BLOCKED_MIMES = frozenset({
    "text/html", "image/svg+xml", "application/xhtml+xml",
    "application/javascript", "text/javascript", "application/x-msdownload",
    "application/x-executable", "application/x-sh", "application/x-bat",
})
EXTENSIONS = {
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
    "image/gif": (".gif",),
    "image/webp": (".webp",),
    "video/mp4": (".mp4",),
    "video/webm": (".webm",),
    "audio/ogg": (".ogg", ".oga", ".opus"),
    "audio/webm": (".webm",),
    "audio/mpeg": (".mp3",),
    "audio/mp4": (".m4a", ".mp4"),
    "audio/wav": (".wav",),
    "application/pdf": (".pdf",),
    "application/zip": (".zip",),
}


def _signature_valid(content: bytes, mime: str) -> bool:
    if mime == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if mime == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/gif":
        return content.startswith((b"GIF87a", b"GIF89a"))
    if mime == "image/webp":
        return content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    if mime in {"audio/webm", "video/webm"}:
        return content.startswith(b"\x1a\x45\xdf\xa3")
    if mime in {"audio/mp4", "video/mp4"}:
        return len(content) >= 12 and content[4:8] == b"ftyp"
    if mime == "audio/ogg":
        return content.startswith(b"OggS")
    if mime == "audio/mpeg":
        return content.startswith(b"ID3") or (
            len(content) >= 2 and content[0] == 0xff and content[1] & 0xe0 == 0xe0
        )
    if mime == "audio/wav":
        return content.startswith(b"RIFF") and content[8:12] == b"WAVE"
    if mime == "application/pdf":
        return content.startswith(b"%PDF-")
    if mime in {"application/zip"} or mime.endswith((
        ".wordprocessingml.document", ".spreadsheetml.sheet",
        ".presentationml.presentation",
    )):
        return content.startswith(b"PK\x03\x04")
    # A generic native document is downloadable, not parsed or executed.
    return not content.startswith((
        b"MZ", b"\x7fELF", b"#!", b"%PDF-", b"\x89PNG\r\n\x1a\n",
        b"\xff\xd8\xff", b"GIF87a", b"GIF89a",
    ))


def verify_media(
    *, content: bytes, filename: str, content_type: str,
    size: int, sha256: str, uploaded_name: str | None = None,
    uploaded_mime: str | None = None, kind: str = "document",
) -> bool:
    """Validate manifest + bytes, return native image-preview flag.

    ValueError is deliberately generic: the HTTP boundary maps it to
    invalid_media without echoing any untrusted filename/content.
    """
    if (
        not isinstance(filename, str)
        or not 0 < len(filename) <= 200
        or filename != safe_filename(filename)
        or filename.lower().endswith(BLOCKED_SUFFIXES)
        or not isinstance(content_type, str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*", content_type)
        or content_type in BLOCKED_MIMES
        or type(size) is not int
        or not 0 < size <= (MAX_VOICE_BYTES if kind == "voice" else MAX_FILE_BYTES)
        or not isinstance(sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", sha256)
        or not isinstance(content, bytes)
        or len(content) != size
        or hashlib.sha256(content).hexdigest() != sha256
        or (uploaded_name is not None and uploaded_name != filename)
        or (uploaded_mime is not None and uploaded_mime != content_type)
    ):
        raise ValueError("invalid_media")
    lower = filename.lower()
    if content_type in EXTENSIONS and not lower.endswith(EXTENSIONS[content_type]):
        raise ValueError("invalid_media")
    expected, _ = mimetypes.guess_type(filename)
    # When filename has a well-known type, an unrelated MIME is an attempt to
    # bypass the signature policy. Octet-stream is permitted only for unknown
    # extensions, never to downgrade a known image/audio/video signature.
    if expected and expected != content_type:
        aliases = {
            ("application/zip", "application/x-zip-compressed"),
            ("audio/mpeg", "audio/mp3"),
            ("audio/x-wav", "audio/wav"),
            ("video/webm", "audio/webm"),
            ("video/mp4", "audio/mp4"),
        }
        if (expected, content_type) not in aliases:
            raise ValueError("invalid_media")
    if kind == "image" and content_type not in IMAGE_MIMES:
        raise ValueError("invalid_media")
    if kind == "voice" and content_type not in VOICE_MIMES:
        raise ValueError("invalid_media")
    if kind == "audio" and content_type not in VOICE_MIMES:
        raise ValueError("invalid_media")
    if kind == "video" and content_type not in VIDEO_MIMES:
        raise ValueError("invalid_media")
    if kind == "animation" and content_type not in IMAGE_MIMES | VIDEO_MIMES:
        raise ValueError("invalid_media")
    if not _signature_valid(content, content_type):
        raise ValueError("invalid_media")
    return content_type in IMAGE_MIMES
