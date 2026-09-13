# Онбординг «Начало работы» показывается всем, кто его ещё не закрыл, включая
# тех, кто работает в установке давно. Признак закрытия — на членстве человека
# в организации: у каждого он свой, и закрытие одним администратором не прячет
# визард у остальных. NULL по умолчанию, поэтому существующие записи считаются
# «не закрывал» и увидят визард при следующем входе.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0037_invitation_membership_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationmembership",
            name="onboarding_dismissed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="organizationmembership",
            name="onboarding_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
