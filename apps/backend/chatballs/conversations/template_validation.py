"""Validation shared by reply template HTTP operations."""

import re

from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException

from chatballs.conversations.template_models import (
    ReplyTemplateCategory,
    ReplyTemplateTag,
)
from chatballs.i18n import t

TEMPLATE_VARIABLES = frozenset({"client_name", "operator_name", "company"})
_TEMPLATE_TOKEN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class LibraryValidationError(APIException):
    status_code = 400


ValidationError = LibraryValidationError


class NameConflict(APIException):
    status_code = 409

    def __init__(self):
        super().__init__(t("conversations.template_name_taken"))


def library_name(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 120:
        raise ValidationError(t("conversations.template_name_length"))
    return value.strip()


def template_text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(t("conversations.template_text_required"))
    unknown = sorted({
        match.group(0) for match in _TEMPLATE_TOKEN.finditer(value)
        if match.group(1) not in TEMPLATE_VARIABLES
    })
    if unknown:
        raise ValidationError(t("conversations.template_unknown_variables", names=", ".join(unknown)))
    return value.strip()


def save_named(instance, name_field):
    if type(instance).objects.filter(
        organization_id=instance.organization_id, owner_id=instance.owner_id,
        **{f"{name_field}__iexact": getattr(instance, name_field)},
    ).exclude(pk=instance.pk).exists():
        raise NameConflict()
    try:
        with transaction.atomic():
            instance.save()
    except IntegrityError as error:
        if getattr(error.__cause__, "sqlstate", None) == "23505":
            raise NameConflict() from None
        raise


def template_relations(template, data):
    filters = {"organization_id": template.organization_id, "owner_id": template.owner_id}
    if "categoryId" in data:
        category_id = data["categoryId"]
        if category_id is None:
            template.category = None
        elif type(category_id) is not int or not (category := ReplyTemplateCategory.objects.filter(
            pk=category_id, **filters,
        ).first()):
            raise ValidationError(t("conversations.template_relation_invalid"))
        else:
            template.category = category
    if "tagIds" not in data:
        return None
    ids = data["tagIds"]
    if not isinstance(ids, list) or any(type(pk) is not int for pk in ids):
        raise ValidationError(t("conversations.template_relation_invalid"))
    ids = set(ids)
    tags = list(ReplyTemplateTag.objects.filter(pk__in=ids, **filters))
    if len(tags) != len(ids):
        raise ValidationError(t("conversations.template_relation_invalid"))
    return tags
