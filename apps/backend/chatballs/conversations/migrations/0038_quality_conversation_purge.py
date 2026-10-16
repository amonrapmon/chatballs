from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("conversations", "0037_merge_quality_reporting")]
    operations = [migrations.AlterField(
        model_name="qualityjob", name="conversation",
        field=models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING,
                                to="conversations.conversation"),
    )]
