"""Flat category and tag operations use the same library access rules."""

from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.api.permissions import HasCapability
from chatballs.conversations.template_access import (
    creation_owner,
    library_object,
    require_library_management,
    validate_unchanged_scope,
    visible_library,
)
from chatballs.conversations.template_models import (
    ReplyTemplateCategory,
    ReplyTemplateTag,
)
from chatballs.conversations.template_validation import library_name, save_named


def taxonomy_payload(item):
    return {"id": item.pk, "name": item.name, "scope": item.scope, "ownerId": item.owner_id}


class TaxonomyListView(APIView):
    permission_classes = [HasCapability]
    required_capability = "conversations.view"
    model = None

    def get(self, request):
        return Response({"items": [taxonomy_payload(item) for item in visible_library(
            self.model, request.tenant_context.membership,
        )]})

    def post(self, request):
        actor = request.tenant_context.membership
        item = self.model(
            organization_id=actor.organization_id, owner_id=creation_owner(actor, request.data),
            name=library_name(request.data.get("name")),
        )
        validate_unchanged_scope(item, request.data)
        save_named(item, "name")
        return Response({"item": taxonomy_payload(item)}, status=201)


class TaxonomyDetailView(APIView):
    permission_classes = [HasCapability]
    required_capability = "conversations.view"
    model = None

    def get(self, request, item_id):
        return Response({"item": taxonomy_payload(library_object(
            self.model, request.tenant_context.membership, item_id,
        ))})

    def patch(self, request, item_id):
        actor = request.tenant_context.membership
        item = library_object(self.model, actor, item_id)
        require_library_management(actor, item.owner_id)
        validate_unchanged_scope(item, request.data)
        item.name = library_name(request.data.get("name", item.name))
        save_named(item, "name")
        return Response({"item": taxonomy_payload(item)})

    def delete(self, request, item_id):
        actor = request.tenant_context.membership
        item = library_object(self.model, actor, item_id)
        require_library_management(actor, item.owner_id)
        item.delete()
        return Response(status=204)


class CategoryListView(TaxonomyListView):
    model = ReplyTemplateCategory


class CategoryDetailView(TaxonomyDetailView):
    model = ReplyTemplateCategory


class TagListView(TaxonomyListView):
    model = ReplyTemplateTag


class TagDetailView(TaxonomyDetailView):
    model = ReplyTemplateTag
