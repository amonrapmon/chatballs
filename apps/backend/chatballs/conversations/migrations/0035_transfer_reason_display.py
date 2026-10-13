from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("conversations", "0034_initial_assignment_policy")]

    operations = [
        migrations.AddField(
            model_name="transferreason", name="previous_name",
            field=models.CharField(blank=True, default="", max_length=120),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="transferreason", name="renamed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
