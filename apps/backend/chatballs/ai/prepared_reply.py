"""In-memory customer snapshot; never carries render arguments or ORM references."""

import json
from dataclasses import dataclass, field

from chatballs.ai.runtime import HANDOFF_TOKEN

PREPARED_PREFIX = "CHATBALLS_PREPARED:"


@dataclass(frozen=True, slots=True)
class PreparedReply:
    text: str = field(repr=False)
    content_html: str = field(repr=False)
    presentation_json: str = field(repr=False)
    template_json: str

    def payload(self, *, representation="html"):
        return {
            "contentHtml": self.content_html,
            "presentation": json.loads(self.presentation_json),
            "deliveryRepresentation": representation,
            "template": json.loads(self.template_json),
        }

    def message_fields(self, *, representation):
        return {
            "content_html": self.content_html,
            "presentation": json.loads(self.presentation_json),
            "format_version": 1,
            "delivery_representation": representation,
            "template_snapshot": json.loads(self.template_json),
        }


def final_selection(text, prepared):
    """Only an exact server-issued reference can select a prepared response."""
    selector = text.replace(HANDOFF_TOKEN, "").strip()
    if PREPARED_PREFIX not in selector:
        return None
    return prepared.get(selector)
