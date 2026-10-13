from django.db import migrations, models
from django.db.models.functions import Now


class Migration(migrations.Migration):
    dependencies = [("conversations", "0035_report_source_boundary"), ("tenancy", "0047_work_status_block_stop")]
    operations = [migrations.AddField(
        model_name="conversationeventhistorystart", name="status_stops_available_from",
        field=models.DateTimeField(db_default=Now(), editable=False),
    )]
