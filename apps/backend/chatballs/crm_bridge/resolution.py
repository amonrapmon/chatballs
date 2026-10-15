"""Read-only CRM link resolution, always scoped to caller-visible conversations."""

from __future__ import annotations

from chatballs.conversations.models import Contact
from chatballs.conversations.selectors import (
    conversation_for_context,
    visible_conversations_for,
)

from chatballs.crm_bridge.models import (
    CRMCompany,
    CRMConnectionBinding,
    CRMOrganizationConfig,
    CRMProvider,
)
from chatballs.crm_bridge.search_urls import build_client_search_url
from chatballs.tenancy.context import TenantContext


def _active_provider(organization_id: int) -> str:
    return (
        CRMOrganizationConfig.objects.filter(organization_id=organization_id)
        .values_list("provider", flat=True).first()
        or CRMProvider.NONE
    )


def _company_for_connection(organization_id: int, connection_id: int | None):
    """Explicit mapping wins; fallback ONLY with exactly one active company."""
    bound = (
        CRMConnectionBinding.objects.filter(
            organization_id=organization_id, integration_id=connection_id
        ).select_related("crm_company").first()
        if connection_id is not None else None
    )
    if bound is not None:
        if bound.crm_company.is_active:
            return bound.crm_company, "ok"
        return None, "inactive_company"

    active = list(
        CRMCompany.objects.filter(organization_id=organization_id, is_active=True)
        .order_by("pk")[:2]
    )
    if len(active) == 1:
        return active[0], "ok"
    return None, "ambiguous_company" if active else "no_company"


def _link(company: CRMCompany, provider: str, phone: str | None) -> dict | None:
    url = build_client_search_url(provider, company.external_company_id, phone)
    if url is None:
        return None
    return {
        "companyId": company.pk,
        "companyName": company.name,
        "provider": provider,
        "url": url,
    }


def links_for_conversation(*, context: TenantContext, conversation_id: int) -> dict:
    """Selector enforces group/assignment visibility, not just organization FK."""
    conversation = conversation_for_context(
        context=context, conversation_id=conversation_id
    )
    provider = _active_provider(context.organization_id)
    if provider == CRMProvider.NONE:
        return {"state": "disabled", "links": []}
    if conversation.contact is None:
        return {"state": "no_phone", "links": []}
    company, reason = _company_for_connection(context.organization_id, conversation.connection_id)
    if company is None:
        return {"state": reason, "links": []}
    link = _link(company, provider, conversation.contact.phone)
    if link is None:
        return {"state": "no_phone", "links": []}
    return {"state": "ok", "links": [link]}


def links_for_contact(*, context: TenantContext, contact_id: int) -> dict:
    """Use only visible dialogs for contact and branch resolution."""
    visible = visible_conversations_for(context).filter(contact_id=contact_id)
    connection_ids = list(visible.values_list("connection_id", flat=True).distinct())
    if not connection_ids:
        raise Contact.DoesNotExist
    contact = Contact.objects.get(id=contact_id, organization_id=context.organization_id)
    provider = _active_provider(context.organization_id)
    if provider == CRMProvider.NONE:
        return {"state": "disabled", "links": []}
    links_by_company: dict[int, dict] = {}
    unresolved = False
    for connection_id in connection_ids:
        company, _reason = _company_for_connection(context.organization_id, connection_id)
        if company is None:
            unresolved = True
            continue
        link = _link(company, provider, contact.phone)
        if link is None:
            return {"state": "no_phone", "links": []}
        links_by_company[company.pk] = link
    links = sorted(links_by_company.values(), key=lambda item: (item["companyName"], item["companyId"]))
    if unresolved:
        return {"state": "partial" if links else "ambiguous_company", "links": links}
    return {"state": "multiple_companies" if len(links) > 1 else "ok", "links": links}
