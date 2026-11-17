"""The reporting directory projects messenger identity; historical transport stays native."""

from chatballs.conversations.report_directory import report_directory
from chatballs.conversations.support_report_test_base import SupportReportTestBase
from chatballs.integrations.models import Integration


class ReportDirectoryPlatformTests(SupportReportTestBase):
    def test_connector_messenger_is_presentation_only(self):
        for name, service in (
            ("TG via Connector", "green_api_telegram"),
            ("MAX via Connector", "green_api_max"),
            ("Custom API", "custom_adapter"),
        ):
            Integration.objects.create(
                organization=self.organization,
                kind="MESSENGER",
                provider="API_CONNECTOR",
                name=name,
                config={"connector_service": service},
            )

        directory = report_directory(self.context)
        connections = {row["name"]: row for row in directory["connections"]}
        self.assertEqual(connections["TG via Connector"]["provider"], "API_CONNECTOR")
        self.assertEqual(connections["TG via Connector"]["displayProvider"], "TELEGRAM")
        self.assertEqual(connections["MAX via Connector"]["provider"], "API_CONNECTOR")
        self.assertEqual(connections["MAX via Connector"]["displayProvider"], "MAX")
        self.assertEqual(connections["Custom API"]["displayProvider"], "API_CONNECTOR")
        self.assertEqual(connections["Web"]["displayProvider"], "WEB")

        self.assertTrue(Integration.objects.filter(
            organization=self.organization,
            name="TG via Connector",
            provider="API_CONNECTOR",
            config__connector_service="green_api_telegram",
        ).exists())
