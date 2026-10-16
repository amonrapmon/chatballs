"""Saved contact addresses and usable organization mailboxes; never expose config."""

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from chatballs.conversations.models import ConnectionIdentity
from chatballs.integrations.models import Integration


def saved_addresses(conversation):
    if not conversation.contact_id:
        return []
    addresses = {conversation.contact.email.strip().lower()}
    addresses.update(value.strip().lower() for value in ConnectionIdentity.objects.filter(
        organization_id=conversation.organization_id, contact_id=conversation.contact_id,
        connection__provider="EMAIL",
    ).values_list("external_user_id", flat=True))
    result = []
    for address in sorted(addresses):
        try:
            validate_email(address)
        except ValidationError:
            continue
        result.append(address)
    return result


def mailbox_available(connection):
    """WEB continuation uses its original agent, not the mailbox's inbound route."""
    return bool(
        connection.kind == "MESSENGER" and connection.provider == "EMAIL"
        and connection.status != "ERROR"
        and connection.is_active
        and connection.secret and connection.config.get("smtp_host")
        and connection.config.get("imap_host") and connection.config.get("email")
        and not connection.config.get("demoSeed")
    )


def letter_mailbox_available(letter):
    return mailbox_available(letter.connection) and (
        not letter.sender_address or letter.sender_address == letter.connection.config["email"].strip().lower()
    )


def available_mailboxes(organization_id):
    return [connection for connection in Integration.objects.filter(
        organization_id=organization_id, kind="MESSENGER", provider="EMAIL", is_active=True,
    ).select_related("channel") if mailbox_available(connection)]
