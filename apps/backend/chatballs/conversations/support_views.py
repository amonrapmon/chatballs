"""Report endpoints intentionally independent of a future report UI."""

from django.http import HttpResponse
from rest_framework.response import Response

from chatballs.conversations.report_directory import report_directory
from chatballs.conversations.support_export import export_csv, export_xlsx
from chatballs.conversations.support_filters import parse_filters
from chatballs.conversations.support_report import calculate_support_report
from chatballs.conversations.view_base import ConversationViewBase


class SupportReportView(ConversationViewBase):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def get(self, request):
        return Response(calculate_support_report(context=request.tenant_context,
                                                 filters=parse_filters(request.query_params)))


class SupportCSVView(ConversationViewBase):
    def get(self, request):
        return self.export(request, export_csv, "text/csv; charset=utf-8", "csv")

    def export(self, request, exporter, content_type, extension):
        report = calculate_support_report(context=request.tenant_context, filters=parse_filters(request.query_params))
        response = HttpResponse(exporter(report), content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="support-report.{extension}"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class SupportReportAccessView(SupportReportView):
    def get(self, request):
        return Response(report_directory(request.tenant_context))


class SupportXLSXView(SupportCSVView):
    def get(self, request):
        return self.export(request, export_xlsx,
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx")
