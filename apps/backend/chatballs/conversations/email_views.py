"""Mail continuation is a staff API, independent of visitor signals and UI."""

from rest_framework import serializers
from rest_framework.response import Response

from chatballs.api.pagination import cursor_id, window_size
from chatballs.conversations.email_attempt_models import EmailSendOperation
from chatballs.conversations.email_continuation import (
    require_reply,
    retry_email_reply,
    send_email_reply,
)
from chatballs.conversations.email_options import available_mailboxes, saved_addresses
from chatballs.conversations.email_payloads import attempt_payload, operation_payload
from chatballs.conversations.models import Conversation
from chatballs.conversations.services import ClaimError
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.i18n import t


class SendInput(serializers.Serializer):
    recipient = serializers.EmailField()
    connectionId = serializers.IntegerField(min_value=1)
    text = serializers.CharField(max_length=20000)
    clientKey = serializers.CharField(max_length=128)
    subject = serializers.CharField(max_length=998, required=False, allow_blank=True, default="")


class RetryInput(serializers.Serializer):
    acknowledgeUnknown = serializers.BooleanField(default=False)


class EmailOptionsView(ConversationViewBase):
    required_capability = "conversations.operate"

    def get(self, request, conversation_id):
        try:
            conversation = self._conversation(request, conversation_id, self.required_capability)
            require_reply(request.tenant_context, conversation, allow_unclaimed=True)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        except ClaimError as error:
            return Response({"detail": str(error)}, status=409)
        return Response({
            "addresses": saved_addresses(conversation),
            "mailboxes": [{"id": connection.pk, "name": connection.name, "address": connection.config["email"]}
                          for connection in available_mailboxes(conversation.organization_id)],
        })


class EmailOperationsView(ConversationViewBase):
    required_capabilities = {"GET": "conversations.view", "POST": "conversations.operate"}

    def get(self, request, conversation_id):
        try:
            conversation = self._conversation(request, conversation_id)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        operations = EmailSendOperation.objects.filter(
            organization_id=conversation.organization_id, letter__thread__conversation=conversation,
        ).select_related("letter__thread", "letter__connection__channel", "initiated_by").order_by("-pk")
        limit = window_size(request.query_params, default=50)
        before = cursor_id(request.query_params, "before")
        if before is not None:
            operations = operations.filter(pk__lt=before)
        rows = list(operations[:limit + 1])
        return Response({"items": [operation_payload(row, context=request.tenant_context) for row in rows[:limit]],
                         "nextCursor": rows[limit - 1].pk if len(rows) > limit else None})

    def post(self, request, conversation_id):
        data = SendInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            operation, created = send_email_reply(
                context=request.tenant_context, conversation_id=conversation_id,
                recipient=values["recipient"], connection_id=values["connectionId"],
                text=values["text"], client_key=values["clientKey"], subject=values["subject"],
            )
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        except ClaimError as error:
            return Response({"detail": str(error)}, status=409)
        return Response({"operation": operation_payload(operation, context=request.tenant_context)}, status=201 if created else 200)


class EmailRetryView(ConversationViewBase):
    required_capability = "conversations.operate"

    def post(self, request, conversation_id, operation_id):
        data = RetryInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            attempt = retry_email_reply(
                context=request.tenant_context, conversation_id=conversation_id,
                operation_id=operation_id, acknowledge_unknown=data.validated_data["acknowledgeUnknown"],
            )
        except (Conversation.DoesNotExist, EmailSendOperation.DoesNotExist):
            return Response({"detail": t("conversations.not_found")}, status=404)
        except ClaimError as error:
            return Response({"detail": str(error)}, status=409)
        return Response({"attempt": attempt_payload(attempt)}, status=201)
