"""Allow API Connector as a domain-event transport without truncation."""
from django.db import migrations, models
from django.db.models import Q


TRANSPORTS = [
    ("MAX", "MAX"),
    ("TELEGRAM", "TELEGRAM"),
    ("VK", "VK"),
    ("WEB", "WEB"),
    ("EMAIL", "EMAIL"),
    ("API_CONNECTOR", "API_CONNECTOR"),
]


class Migration(migrations.Migration):
    dependencies = [("conversations", "0048_connector_route_identity")]

    operations = [
        migrations.AlterField(
            model_name="conversationevent",
            name="transport",
            field=models.CharField(
                max_length=16, choices=TRANSPORTS, null=True, blank=True,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="conversationevent",
            name="domain_event_transport_valid",
        ),
        migrations.AddConstraint(
            model_name="conversationevent",
            constraint=models.CheckConstraint(
                condition=Q(transport__isnull=True) |
                Q(transport__in=["MAX", "TELEGRAM", "VK", "WEB", "EMAIL", "API_CONNECTOR"]),
                name="domain_event_transport_valid",
            ),
        ),
    ]
