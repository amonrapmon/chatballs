"""Reply template CRUD; scope is resolved from the authenticated membership."""

from django.db import transaction
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
from chatballs.conversations.template_models import ReplyTemplate, ReplyTemplateTagLink
from chatballs.conversations.template_validation import (
    library_name,
    save_named,
    template_relations,
    template_text,
)


def template_payload(template):
    return {
        "id": template.pk, "title": template.title, "text": template.text,
        "updatedAt": template.updated_at.isoformat(), "scope": template.scope,
        "ownerId": template.owner_id, "categoryId": template.category_id,
        "tagIds": [tag.pk for tag in template.tags.all()],
    }


def save_template(template, data):
    validate_unchanged_scope(template, data)
    if "title" in data or not template.pk:
        template.title = library_name(data.get("title"))
    if "text" in data or not template.pk:
        template.text = template_text(data.get("text"))
    tags = template_relations(template, data)
    with transaction.atomic():
        save_named(template, "title")
        if tags is not None:
            ReplyTemplateTagLink.objects.filter(template=template).delete()
            ReplyTemplateTagLink.objects.bulk_create([
                ReplyTemplateTagLink(organization_id=template.organization_id, template=template, tag=tag)
                for tag in tags
            ])


class ReplyTemplateListView(APIView):
    permission_classes = [HasCapability]
    required_capability = "conversations.view"

    def get(self, request):
        templates = visible_library(ReplyTemplate, request.tenant_context.membership).prefetch_related("tags")
        return Response({"items": [template_payload(item) for item in templates]})

    def post(self, request):
        actor = request.tenant_context.membership
        template = ReplyTemplate(
            organization_id=actor.organization_id, owner_id=creation_owner(actor, request.data),
        )
        save_template(template, request.data)
        return Response({"template": template_payload(template)}, status=201)


class ReplyTemplateDetailView(APIView):
    permission_classes = [HasCapability]
    required_capability = "conversations.view"

    def get(self, request, template_id):
        return Response({"template": template_payload(library_object(
            ReplyTemplate, request.tenant_context.membership, template_id,
        ))})

    def patch(self, request, template_id):
        actor = request.tenant_context.membership
        # Serialize editing with category/tag deletion and other template edits.
        with transaction.atomic():
            template = library_object(ReplyTemplate, actor, template_id)
            template = ReplyTemplate.objects.select_for_update().get(pk=template.pk)
            require_library_management(actor, template.owner_id)
            save_template(template, request.data)
        return Response({"template": template_payload(template)})

    def delete(self, request, template_id):
        actor = request.tenant_context.membership
        template = library_object(ReplyTemplate, actor, template_id)
        require_library_management(actor, template.owner_id)
        template.delete()
        return Response(status=204)
