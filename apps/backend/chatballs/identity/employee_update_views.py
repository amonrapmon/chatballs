from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.i18n import t
from chatballs.identity.audit import record_audit_event
from chatballs.identity.employee_access import (
    resolve_supervised_groups,
    set_groups,
    update_employee_access,
)
from chatballs.identity.employee_support import employee_payload, get_owned_profile
from chatballs.identity.employee_validation import (
    ASSIGNABLE_ROLES,
    clean_position_title,
    deny_employee_action,
    resolve_groups,
)
from chatballs.identity.governance import EmployeeAction, can_manage_employee
from chatballs.identity.models import HumanUser


class EmployeeUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request: Request, user_id: int) -> Response:
        actor = request.tenant_context.membership
        profile = get_owned_profile(request, user_id, for_update=True)
        if profile is None:
            return Response({"detail": t("admin.employee_not_found")}, status=404)
        if not can_manage_employee(actor, profile, EmployeeAction.UPDATE_PROFILE):
            return deny_employee_action(request, profile, EmployeeAction.UPDATE_PROFILE)

        body = request.data
        full_name = str(body.get("fullName", "")).strip()
        email = HumanUser.objects.normalize_email(str(body.get("email", "")).strip())
        phone = str(body.get("phone", "")).strip()
        position_title, position_error = clean_position_title(
            body.get("positionTitle", profile.position_title)
        )
        requested_role = str(body.get("role", profile.role))

        if not full_name:
            return Response({"detail": t("admin.full_name_required")}, status=400)
        if not email:
            return Response({"detail": t("admin.email_required")}, status=400)
        if HumanUser.objects.exclude(id=profile.user_id).filter(email=email).exists():
            return Response({"detail": t("admin.email_taken")}, status=400)
        if position_error:
            return Response({"detail": position_error}, status=400)

        role_changing = requested_role != profile.role
        if role_changing:
            if requested_role not in ASSIGNABLE_ROLES:
                return Response({"detail": t("admin.invalid_role")}, status=400)
            if not can_manage_employee(actor, profile, EmployeeAction.CHANGE_ROLE):
                return deny_employee_action(request, profile, EmployeeAction.CHANGE_ROLE)

        groups, groups_error = resolve_groups(profile.organization, body.get("groupIds"))
        if groups_error:
            return Response({"detail": groups_error}, status=400)
        if groups is not None and not can_manage_employee(
            actor, profile, EmployeeAction.CHANGE_GROUPS
        ):
            return deny_employee_action(request, profile, EmployeeAction.CHANGE_GROUPS)

        supervised_groups, supervision_error = resolve_supervised_groups(
            profile, requested_role, body
        )
        if supervision_error:
            return Response({"detail": supervision_error}, status=400)
        if supervised_groups is not None and not can_manage_employee(
            actor, profile, EmployeeAction.CHANGE_SUPERVISED_GROUPS
        ):
            return deny_employee_action(request, profile, EmployeeAction.CHANGE_SUPERVISED_GROUPS)

        profile.user.full_name = full_name
        profile.user.email = email
        profile.user.save(update_fields=["full_name", "email"])
        profile.phone = phone
        profile.position_title = position_title
        profile.save(update_fields=["phone", "position_title"])
        update_employee_access(request, profile, requested_role, supervised_groups)
        if groups is not None:
            set_groups(profile, groups)

        record_audit_event(
            action="identity.employee_updated",
            actor=request.user,
            organization=profile.organization,
            object_type="HumanUser",
            object_id=str(profile.user_id),
            request=request,
        )
        if groups is not None:
            record_audit_event(
                action="identity.employee_groups_changed",
                actor=request.user,
                organization=profile.organization,
                object_type="HumanUser",
                object_id=str(profile.user_id),
                payload={"groupIds": [group.id for group in groups]},
                request=request,
            )
        return Response({"employee": employee_payload(profile, actor)})
