"""Allow a bounded set of independently staged media parts per provider root."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("conversations", "0057_remove_conversationevent_domain_event_transport_valid_and_more")]

    operations = [
        migrations.RemoveConstraint(
            model_name="connectormediaingest",
            name="connector_media_v1_single_part",
        ),
        migrations.AddConstraint(
            model_name="connectormediaingest",
            constraint=models.CheckConstraint(
                condition=models.Q(part_index__lte=9),
                name="connector_media_max_ten_parts",
            ),
        ),
    ]
