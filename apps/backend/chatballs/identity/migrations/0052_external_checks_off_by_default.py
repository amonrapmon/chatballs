from django.db import migrations, models


def disable_inherited_default(apps, schema_editor):
    instance_settings = apps.get_model("identity", "InstanceSettings")
    # Revision zero is the upstream default, before the first settings change.
    instance_settings.objects.using(schema_editor.connection.alias).filter(
        external_checks_enabled=True,
        external_checks_revision=0,
    ).update(external_checks_enabled=False)


class Migration(migrations.Migration):
    dependencies = [("identity", "0051_membership_dismissal")]

    operations = [
        migrations.AlterField(
            model_name="instancesettings",
            name="external_checks_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(disable_inherited_default, migrations.RunPython.noop),
    ]
