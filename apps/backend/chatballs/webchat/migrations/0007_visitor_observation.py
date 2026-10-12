from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("webchat", "0006_widget_asset")]

    operations = [
        migrations.CreateModel(
            name="VisitorObservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tab_id", models.UUIDField()),
                ("sequence", models.PositiveBigIntegerField()),
                ("widget_state", models.CharField(default="unknown", max_length=16)),
                ("page_state", models.CharField(default="unknown", max_length=16)),
                ("connection_state", models.CharField(default="unknown", max_length=16)),
                ("heartbeat_at", models.DateTimeField(blank=True, null=True)),
                ("received_at", models.DateTimeField()),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organization")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="observations", to="webchat.websession")),
            ],
            options={"constraints": [
                models.UniqueConstraint(fields=("session", "tab_id"), name="uniq_visitor_session_tab"),
                models.CheckConstraint(condition=models.Q(sequence__gte=1), name="visitor_sequence_positive"),
                models.CheckConstraint(condition=models.Q(widget_state__in=("unknown", "open", "closed")), name="visitor_widget_valid"),
                models.CheckConstraint(condition=models.Q(page_state__in=("unknown", "visible", "hidden", "frozen", "resumed", "pagehide", "pageshow")), name="visitor_page_valid"),
                models.CheckConstraint(condition=models.Q(connection_state__in=("unknown", "connected", "lost")), name="visitor_connection_valid"),
            ]},
        ),
    ]
