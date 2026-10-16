import django.db.models.deletion
from django.db import migrations, models

ROLES = [('OWNER', 'Owner'), ('ADMIN', 'Admin'), ('SUPERVISOR', 'Supervisor'), ('EMPLOYEE', 'Employee')]


class Migration(migrations.Migration):
    dependencies = [('identity', '0042_organization_participant_limit')]
    operations = [
        migrations.AlterField(
            model_name='organizationmembership', name='role',
            field=models.CharField(choices=ROLES, max_length=32),
        ),
        migrations.AlterField(
            model_name='organizationinvitation', name='role',
            field=models.CharField(choices=ROLES, max_length=32),
        ),
        migrations.CreateModel(
            name='EmployeeGroupSupervision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.organization')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='supervision_links', to='identity.organizationmembership')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='supervision_links', to='identity.employeegroup')),
            ],
            options={'constraints': [models.UniqueConstraint(fields=('group', 'employee'), name='uniq_employee_group_supervision')]},
        ),
    ]
