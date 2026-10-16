"""Фото только автора клиентского сообщения, доступного текущей web-сессии."""

from django.db.models import Exists, OuterRef

from chatballs.conversations.models import MessageAuthor
from chatballs.identity.models import OrganizationMembership


def with_operator_authors(messages, session):
    return messages.select_related("author_user").annotate(
        author_in_organization=Exists(OrganizationMembership.objects.filter(
            organization_id=session.organization_id, user_id=OuterRef("author_user_id"),
        )),
    )


def operator_author(message):
    if message.author_type == MessageAuthor.OPERATOR and message.author_in_organization:
        return message.author_user
    return None


def author_payload(message):
    author = operator_author(message)
    return {
        "authorName": author.full_name if author else "",
        "hasAuthorAvatar": bool(author and author.avatar),
    }
