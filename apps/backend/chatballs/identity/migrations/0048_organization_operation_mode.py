from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("identity", "0047_merge_rule_actions_main")]

    operations = [
        migrations.AddField(
            model_name="organization", name="operation_mode",
            field=models.CharField(max_length=16, default="AI_AGENTS",
                                   choices=[("AI_AGENTS", "AI agents"), ("OPERATORS_ONLY", "Operators only")]),
        ),
        migrations.AddField(
            model_name="organization", name="operation_mode_version",
            field=models.PositiveBigIntegerField(default=1),
        ),
    ]
