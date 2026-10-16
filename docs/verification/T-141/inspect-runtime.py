"""Read existing data under the runtime DB role; no seed, writes or AI calls."""

import json
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from chatballs.conversations.models import Conversation
from chatballs.conversations.support_views import SupportReportView
from chatballs.identity.models import OrganizationMembership
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


with transaction.atomic():
    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute("SELECT current_user")
        role = cursor.fetchone()[0]
    with tenant_atomic(1):
        manager = OrganizationMembership.objects.filter(
            role__in=["OWNER", "ADMIN"], blocked_at__isnull=True, user__is_active=True,
        ).select_related("organization", "user").first()
        assert manager is not None, "No existing manager in organization 1"
        context = TenantContext.for_membership(manager)
        first = Conversation.objects.earliest("created_at")
        request = APIRequestFactory().get("/", {
            "from": (first.created_at - timedelta(seconds=1)).isoformat(),
            "to": timezone.now().isoformat(), "timezone": "UTC",
        })
        request.tenant_context = context
        force_authenticate(request, user=manager.user)
        response = SupportReportView.as_view()(request)
        assert response.status_code == 200, response.status_code
        data = response.data
        print(json.dumps({
            "transaction": "READ ONLY", "databaseRole": role, "httpStatus": response.status_code,
            "conversations": Conversation.objects.count(),
            "ratingCount": data["customerRatings"]["count"],
            "scaleSummaryCount": len(data["customerRatings"]["scaleSummaries"]),
            "qualityCount": data["qualityAnalysis"]["count"],
            "versionCount": len(data["qualityAnalysis"]["versions"]),
            "qualityStates": data["qualityAnalysis"]["states"],
        }))
