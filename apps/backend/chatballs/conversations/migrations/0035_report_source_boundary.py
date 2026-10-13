from django.db import migrations, models
from django.db.models.functions import Now


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0034_comment_parent_cascade"),
        ("tenancy", "0046_merge_domain_event_guards"),
    ]
    operations = [migrations.AddField(
        model_name="conversationeventhistorystart", name="sources_available_from",
        field=models.DateTimeField(db_default=Now(), editable=False),
    )]
