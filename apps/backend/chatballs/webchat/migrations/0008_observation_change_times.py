from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("webchat", "0007_visitor_observation")]
    operations = [migrations.AddField(
        model_name="visitorobservation", name=name,
        field=models.DateTimeField(null=True, blank=True),
    ) for name in ("widget_changed_at", "page_changed_at", "connection_changed_at")]
