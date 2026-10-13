"""Read-only inspection of existing organization data and real quality APIs."""

from datetime import timedelta
from contextlib import ExitStack

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from chatballs.conversations.models import Conversation
from chatballs.conversations.quality.access import quality_scope
from chatballs.conversations.quality.views import QualityReportView, QualitySettingsView
from chatballs.identity.models import OrganizationMembership
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


class Command(BaseCommand):
    help = "Verify quality settings/report on existing data in a READ ONLY transaction."

    def add_arguments(self, parser):
        parser.add_argument("--organization-id", type=int)

    def handle(self, *args, **options):
        with transaction.atomic(), ExitStack() as stack:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SELECT current_user")
                database_role = cursor.fetchone()[0]
            if options["organization_id"]:
                stack.enter_context(tenant_atomic(options["organization_id"]))
            manager = OrganizationMembership.objects.filter(
                role__in=["OWNER", "ADMIN"], blocked_at__isnull=True, user__is_active=True,
                organization__conversations__isnull=False,
            ).select_related("organization", "user").distinct().order_by("organization_id", "pk").first()
            if manager is None:
                raise CommandError("No existing active manager with conversations.")
            context = TenantContext.for_membership(manager)
            factory = APIRequestFactory()

            def request(view, params):
                http = factory.get("/", params)
                http.tenant_context = context
                force_authenticate(http, user=manager.user)
                response = view.as_view()(http)
                if response.status_code != 200:
                    raise CommandError(f"Quality API returned HTTP {response.status_code}.")
                return response.data

            with tenant_atomic(context):
                conversations = quality_scope(context)
                first = conversations.earliest("created_at")
                settings = request(QualitySettingsView, {})
                params = {"from": (first.created_at - timedelta(seconds=1)).isoformat(),
                          "to": timezone.now().isoformat(), "timezone": "UTC"}
                report = request(QualityReportView, params)
                allowed = set(conversations.values_list("pk", flat=True))
                for row in report["jobs"]:
                    if row["conversationId"] not in allowed or not row["criteriaVersion"] or not row["criteria"]:
                        raise CommandError("Report scope or criteria snapshot is invalid.")
                self.stdout.write(self.style.SUCCESS(
                    f"READ ONLY: database_role={database_role}, organization={context.organization_id}, "
                    f"conversations={len(allowed)}, "
                    f"enabled={settings['enabled']}, report_jobs={len(report['jobs'])}; "
                    "settings and versioned report APIs returned HTTP 200. No data or accounts changed."
                ))
