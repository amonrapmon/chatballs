"""Tenant API for composition and its immutable, paginated journal."""

from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from chatballs.api.pagination import page_payload, paginate
from chatballs.conversations.models import Conversation
from chatballs.conversations.participant_services import (
    add_participant,
    participation_history,
    remove_participant,
)
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.i18n import t
from chatballs.identity.models import Organization
from chatballs.identity.policy import ResourceScope, authorize


class JoinInput(serializers.Serializer):
    membershipId = serializers.IntegerField(min_value=1)
    reason = serializers.CharField()


class LeaveInput(serializers.Serializer):
    reason = serializers.CharField()


class LimitInput(serializers.Serializer):
    additionalParticipantLimit = serializers.IntegerField(min_value=0, max_value=2147483647)


def participant_payload(participant):
    return {
        "id": participant.pk,
        "membershipId": participant.membership_id,
        "userId": participant.membership.user_id,
        "joinedByMembershipId": participant.joined_by_id,
        "joinedAt": participant.joined_at.isoformat(),
        "joinReason": participant.join_reason,
        "leftByMembershipId": participant.left_by_id,
        "leftAt": participant.left_at.isoformat() if participant.left_at else None,
        "leaveReason": participant.leave_reason,
    }


def not_found():
    return Response({"detail": t("conversations.not_found")}, status=404)


class ParticipantListView(ConversationViewBase):
    required_capabilities = {"GET": "conversations.view", "POST": "conversations.participants"}

    def get(self, request, conversation_id):
        try:
            history = participation_history(context=request.tenant_context, conversation_id=conversation_id)
        except Conversation.DoesNotExist:
            return not_found()
        return Response({"items": [participant_payload(row) for row in history.active()]})

    def post(self, request, conversation_id):
        data = JoinInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            participant, created = add_participant(
                context=request.tenant_context, conversation_id=conversation_id,
                membership_id=data.validated_data["membershipId"], reason=data.validated_data["reason"],
            )
        except Conversation.DoesNotExist:
            return not_found()
        return Response({"participant": participant_payload(participant)}, status=201 if created else 200)


class ParticipantDetailView(ConversationViewBase):
    required_capability = "conversations.participants"

    def delete(self, request, conversation_id, participant_id):
        data = LeaveInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            participant, _ = remove_participant(
                context=request.tenant_context, conversation_id=conversation_id,
                participant_id=participant_id, reason=data.validated_data["reason"],
            )
        except Conversation.DoesNotExist:
            return not_found()
        return Response({"participant": participant_payload(participant)})


class ParticipantHistoryView(ConversationViewBase):
    def get(self, request, conversation_id):
        try:
            history = participation_history(context=request.tenant_context, conversation_id=conversation_id)
        except Conversation.DoesNotExist:
            return not_found()
        return Response(page_payload(paginate(history, request.query_params), participant_payload))


class ParticipantLimitView(ConversationViewBase):
    required_capability = "settings.manage"

    def _organization(self, request):
        context = request.tenant_context
        if not authorize(context.membership, self.required_capability, ResourceScope(context.organization_id)):
            raise PermissionDenied()
        return Organization.objects.select_for_update().get(pk=context.organization_id)

    @transaction.atomic
    def get(self, request):
        organization = self._organization(request)
        return Response({"additionalParticipantLimit": organization.additional_participant_limit})

    @transaction.atomic
    def patch(self, request):
        data = LimitInput(data=request.data)
        data.is_valid(raise_exception=True)
        organization = self._organization(request)
        organization.additional_participant_limit = data.validated_data["additionalParticipantLimit"]
        organization.save(update_fields=["additional_participant_limit"])
        return Response({"additionalParticipantLimit": organization.additional_participant_limit})
