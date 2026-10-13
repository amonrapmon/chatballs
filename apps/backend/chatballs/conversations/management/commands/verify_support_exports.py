"""Read-only acceptance against existing data, never seed or account changes."""

import csv
from datetime import timedelta
from io import BytesIO, StringIO

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIRequestFactory, force_authenticate

from chatballs.conversations.models import Conversation
from chatballs.conversations.support_export import safe_csv_value
from chatballs.conversations.support_export_rows import report_tables
from chatballs.conversations.support_views import SupportCSVView, SupportReportView, SupportXLSXView
from chatballs.i18n import t
from chatballs.identity.models import OrganizationMembership
from chatballs.tenancy.context import TenantContext


class Command(BaseCommand):
    help = "Verify report/API/CSV/XLSX parity on existing data in a READ ONLY transaction."

    def add_arguments(self, parser):
        parser.add_argument("--organization-id", type=int)

    def handle(self, *args, **options):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
            members = OrganizationMembership.objects.filter(
                role__in=["OWNER", "ADMIN"], blocked_at__isnull=True, user__is_active=True,
                organization__conversations__isnull=False,
            ).select_related("organization", "user").distinct().order_by("organization_id", "pk")
            if options["organization_id"]:
                members = members.filter(organization_id=options["organization_id"])
            member = members.first()
            if member is None:
                raise CommandError("No existing active manager with conversations; use the documented backend-admin service.")
            context = TenantContext.for_membership(member)
            first = Conversation.objects.filter(organization=member.organization).earliest("created_at")
            params = {"from": (first.created_at - timedelta(seconds=1)).isoformat(),
                      "to": (timezone.now() - timedelta(seconds=1)).isoformat(), "timezone": "Europe/Moscow"}
            factory = APIRequestFactory()

            def request(view, parameters):
                http_request = factory.get("/", parameters)
                http_request.tenant_context = context
                force_authenticate(http_request, user=member.user)
                response = view.as_view()(http_request)
                if response.status_code != 200:
                    raise CommandError(f"Report returned HTTP {response.status_code}: {getattr(response, 'data', None)}")
                return response

            checked = 0
            variants = [params]
            for key, value in (("employee", member.user_id), ("group", first.group_id),
                               ("connection", first.connection_id),
                               ("transport", first.connection.provider if first.connection_id else None)):
                if value is not None:
                    variants.append({**params, key: value})
            for variant in variants:
                api = request(SupportReportView, variant).data
                csv_response = request(SupportCSVView, variant)
                xlsx_response = request(SupportXLSXView, variant)
                tables = report_tables(api)
                csv_rows = list(csv.reader(StringIO(csv_response.content.decode("utf-8-sig"))))
                # Generation instants differ for separate requests; all selected
                # period data, coverage, units, metrics and details must agree.
                expected_csv = []
                for name, rows in tables:
                    expected_csv.append([t(f"support_stats.sheet.{name}")])
                    expected_csv.extend([[str(safe_csv_value(value)) for value in row] for row in rows])
                    expected_csv.append([])
                generated_label = t("support_stats.generated")
                def clean(rows, label=generated_label):
                    return [row for row in rows if not row or row[0] != label]
                if clean(expected_csv) != clean(csv_rows):
                    raise CommandError("CSV values differ from the API.")
                workbook = load_workbook(BytesIO(xlsx_response.content), data_only=False)
                if len(workbook.worksheets) != len(tables):
                    raise CommandError("Unexpected workbook sheets.")
                for sheet, (_, rows) in zip(workbook, tables, strict=True):
                    expected = [[t("support_stats.unavailable") if value is None else None if value == "" else value
                                 for value in row] for row in rows]
                    actual = [list(row) for row in sheet.values]
                    if clean(expected) != clean(actual):
                        raise CommandError("XLSX values differ from the API.")
                    if any(cell.data_type == "f" for row in sheet for cell in row):
                        raise CommandError("A formula was found in exported data.")
                checked += 1
            self.stdout.write(self.style.SUCCESS(
                f"READ ONLY: organization={member.organization_id}, "
                f"conversations={Conversation.objects.filter(organization=member.organization).count()}, "
                f"parameter_sets={checked}; API/CSV/XLSX values, units, coverage and details match."
            ))
