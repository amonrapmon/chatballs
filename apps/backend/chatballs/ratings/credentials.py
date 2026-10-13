"""Recoverable delivery credential; only its SHA-256 verifier is persisted."""

import hashlib
import hmac
import re

from django.conf import settings


def credential_for(request):
    # Random UUID plus the installation secret makes this opaque/unpredictable.
    # Retries derive the same token without storing it in DB/outbox/messages.
    return hmac.new(
        settings.SECRET_KEY.encode(), f"customer-rating:{request.public_id}".encode(), hashlib.sha256,
    ).hexdigest()


def hash_credential(token):
    return hashlib.sha256(token.encode()).hexdigest()


def bearer_credential(request):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return ""
    token = header[7:]
    return token if re.fullmatch(r"[a-f0-9]{64}", token) else ""
