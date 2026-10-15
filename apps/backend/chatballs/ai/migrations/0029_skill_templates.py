from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai", "0028_skill_library"), ("tenancy", "0067_skill_library_guards")]

    operations = [migrations.AddField(
        model_name="skill", name="templates", field=models.JSONField(default=list),
    )]
