"""Shared read contract: old mail HTML is never promoted to a template snapshot."""


def presentation_payload(message, *, public=False):
    if message.format_version != 1 or message.author_type != "AI":
        return {}
    if public and message.delivery_representation != "html":
        return {}
    return {
        "formatVersion": message.format_version,
        "contentHtml": message.content_html,
        "presentation": message.presentation,
        "deliveryRepresentation": message.delivery_representation,
        "template": message.template_snapshot,
    }
