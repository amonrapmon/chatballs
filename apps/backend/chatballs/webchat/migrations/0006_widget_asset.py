# Иконки кнопки и шапки виджета (SPEC-0021 R-3). RLS, триггеры связей и
# каталог входа для публичной отдачи — в tenancy/0038.

import chatballs.webchat.models
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0040_instance_public_port'),
        ('integrations', '0010_integration_runtime_revision'),
        ('webchat', '0005_remove_widget_mode'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WidgetAsset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('file', models.FileField(max_length=512, upload_to=chatballs.webchat.models.widget_asset_upload_path)),
                ('content_type', models.CharField(max_length=64)),
                ('size', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('integration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='widget_assets', to='integrations.integration')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.organization')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at', '-id'],
            },
        ),
    ]
