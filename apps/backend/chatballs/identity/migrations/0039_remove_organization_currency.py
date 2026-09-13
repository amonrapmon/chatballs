# Валюта организации удалена: поле принимало только RUB, не читалось нигде и
# ни одна сумма в продукте в ней не считалась. Осталось от эпохи CRM и пережило
# пивот в поддержку. Расход на модель — единственные деньги в системе — тоже
# снят вместе с лимитами.
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0038_membership_onboarding_dismissed_at"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="organization",
            name="currency",
        ),
    ]
