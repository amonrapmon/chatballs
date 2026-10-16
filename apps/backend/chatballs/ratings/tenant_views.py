from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.conversations.management_scope import management_scope
from chatballs.ratings.card import conversation_card
from chatballs.ratings.models import RatingSettings
from chatballs.ratings.results import (
    protected_payload,
    results_for_context,
    scale_groups,
)
from chatballs.ratings.settings_service import (
    require_admin,
    settings_payload,
    update_settings,
)


class RatingSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        context = request.tenant_context
        require_admin(context)
        policy = RatingSettings.objects.filter(organization_id=context.organization_id).first()
        return Response(settings_payload(policy or RatingSettings(organization_id=context.organization_id)))

    def patch(self, request):
        return Response(settings_payload(update_settings(request.tenant_context, request.data)))


class ResultFilters(serializers.Serializer):
    responderId = serializers.IntegerField(min_value=1, required=False)
    groupId = serializers.IntegerField(min_value=1, required=False)
    after = serializers.DateTimeField(required=False)
    before = serializers.DateTimeField(required=False)
    offset = serializers.IntegerField(min_value=0, default=0)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=50)


class ProtectedRatingsView(APIView):
    permission_classes = [IsAuthenticated]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class RatingResultsView(ProtectedRatingsView):
    def get(self, request):
        results = results_for_context(request.tenant_context)
        filters = ResultFilters(data=request.query_params)
        filters.is_valid(raise_exception=True)
        data = filters.validated_data
        staff_ids = management_scope(request.tenant_context, forbidden_key="ratings.forbidden").staff_ids()
        if "responderId" in data:
            results = results.filter(request__responder_ids__contains=[data["responderId"]]) if data["responderId"] in staff_ids else results.none()
        if "groupId" in data:
            results = results.filter(request__conversation__group_id=data["groupId"])
        if "after" in data:
            results = results.filter(received_at__gte=data["after"])
        if "before" in data:
            results = results.filter(received_at__lt=data["before"])
        offset, limit = data["offset"], data["limit"]
        return Response({"count": results.count(), "scaleGroups": scale_groups(results.iterator()),
                         "results": [protected_payload(row, permitted_staff_ids=staff_ids) for row in results[offset:offset + limit]]})


class ConversationRatingsView(ProtectedRatingsView):
    def get(self, request, conversation_id):
        return Response(conversation_card(request.tenant_context, conversation_id))
