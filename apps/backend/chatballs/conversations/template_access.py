"""Library access is independent of access to organization settings."""

from django.db.models import Q
from rest_framework.exceptions import NotFound, PermissionDenied

from chatballs.conversations.template_models import ReplyTemplateManagementGrant
from chatballs.conversations.template_validation import (
    LibraryValidationError as ValidationError,
)
from chatballs.i18n import t
from chatballs.identity.policy import can_administer_access, has_capability_any_scope


def can_manage_shared(actor):
    if not has_capability_any_scope(actor, "conversations.view"):
        return False
    return can_administer_access(actor) or ReplyTemplateManagementGrant.objects.filter(
        organization_id=actor.organization_id, membership_id=actor.pk,
    ).exists()


def visible_library(model, actor):
    return model.objects.filter(organization_id=actor.organization_id).filter(
        Q(owner__isnull=True) | Q(owner_id=actor.pk)
    )


def library_object(model, actor, pk):
    try:
        return visible_library(model, actor).get(pk=pk)
    except model.DoesNotExist:
        raise NotFound(t("conversations.template_not_found")) from None


def require_library_management(actor, owner_id):
    if not has_capability_any_scope(actor, "conversations.view") or (
        owner_id != actor.pk and (owner_id is not None or not can_manage_shared(actor))
    ):
        raise PermissionDenied(t("conversations.template_management_denied"))


def creation_owner(actor, data):
    scope = data.get("scope", "SHARED")
    if scope not in ("SHARED", "PERSONAL"):
        raise ValidationError(t("conversations.template_scope_invalid"))
    owner_id = actor.pk if scope == "PERSONAL" else None
    require_library_management(actor, owner_id)
    return owner_id


def validate_unchanged_scope(instance, data):
    if "scope" in data and data["scope"] != instance.scope:
        raise ValidationError(t("conversations.template_scope_immutable"))
    if any(key in data for key in ("owner", "ownerId", "organization", "organizationId")):
        raise ValidationError(t("conversations.template_scope_immutable"))
