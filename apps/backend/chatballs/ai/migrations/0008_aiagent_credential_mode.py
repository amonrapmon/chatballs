# Историческое поле режима доступа к AI; удалено в 0016.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai', '0007_remove_aiagent_is_active_aiagent_lifecycle_version_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='aiagent',
            name='credential_mode',
            field=models.CharField(
                choices=[('BYOK', 'BYOK')],
                default='BYOK',
                max_length=16,
            ),
        ),
    ]
