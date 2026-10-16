from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("conversations", "0032_domain_event_data")]
    operations = [
        migrations.AddField(
            model_name="conversation", name="assignment_version",
            field=models.PositiveBigIntegerField(default=0, db_default=0, editable=False),
        ),
        migrations.AddField(
            model_name="conversationtransfer", name="assignment_version",
            field=models.PositiveBigIntegerField(default=0, db_default=0),
        ),
        migrations.CreateModel(
            name="AssignmentPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ready", models.BooleanField()), ("busy", models.BooleanField()),
                ("break_allowed", models.BooleanField()), ("unavailable", models.BooleanField()),
                ("organization", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to="identity.organization")),
            ],
        ),
    ]
