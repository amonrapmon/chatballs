"""Public context and its fingerprint, bounded before loading message text."""

import hashlib
import json

from chatballs.conversations.history_selectors import customer_visible_messages
from chatballs.conversations.models import MessageAuthor
from chatballs.conversations.selectors import conversation_messages


def history_snapshot(conversation, limit):
    public = customer_visible_messages(conversation_messages(conversation))
    records = list(reversed(public.order_by("-created_at", "-id")[:limit]))
    latest_customer = public.filter(author_type=MessageAuthor.CONTACT).order_by(
        "-created_at", "-id",
    ).first()
    if latest_customer is not None and latest_customer.pk not in {m.pk for m in records}:
        records = [latest_customer, *records[-(limit - 1):]] if limit > 1 else [latest_customer]
    version = hashlib.sha256(json.dumps([
        [m.pk, m.author_type, m.text, m.transcript] for m in records
    ], ensure_ascii=False).encode()).hexdigest()
    roles = {MessageAuthor.CONTACT: "user", MessageAuthor.SYSTEM: "system"}
    history = [{"role": roles.get(m.author_type, "assistant"),
                "content": m.text or m.transcript} for m in records if m.text or m.transcript]
    query = next((m.text or m.transcript for m in reversed(records)
                  if m.author_type == MessageAuthor.CONTACT), "")
    return history, query, version
