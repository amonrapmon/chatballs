from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0026_message_ai_turn_state"),
        ("integrations", "0010_integration_runtime_revision"),
    ]

    operations = [
        migrations.AddField(
            model_name="contact",
            name="email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
        migrations.CreateModel(
            name="ContactFieldValue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=40)),
                ("value", models.JSONField()),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("contact", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="site_field_values", to="conversations.contact")),
                ("integration", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contact_field_values", to="integrations.integration")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organization")),
            ],
            options={
                "db_table": "contact_field_values",
                "constraints": [models.UniqueConstraint(fields=("contact", "integration", "key"), name="uniq_contact_integration_field_key")],
            },
        ),
    ]
