"""Public company branding only; never customer or staff identity."""

from urllib.parse import urlsplit

from chatballs.i18n import customer_language
from chatballs.webchat.appearance import public_appearance
from chatballs.webchat.models import WebSession


def request_presentation(request):
    organization = request.organization
    session = WebSession.objects.filter(
        pk=request.delivery_session_id, organization_id=request.organization_id,
    ).select_related("widget").first()
    widget = session.widget if session else None
    appearance = public_appearance(widget.presentation_config if widget else {})
    origins = widget.allowed_origins if widget else []
    site = next((origin for origin in origins if isinstance(origin, str)
                 and urlsplit(origin).scheme in {"http", "https"}
                 and urlsplit(origin).netloc and not urlsplit(origin).username
                 and not urlsplit(origin).password), "")
    return {
        "name": organization.name, "accent": appearance["accent"],
        "siteUrl": site, "conversationDate": request.completion.occurred_at.isoformat(),
        "language": customer_language(organization),
    }
