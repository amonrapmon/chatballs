"""A null owner preserves every existing template as a shared template."""

import django.db.models.deletion
from django.db import migrations, models
from django.db.models.functions import Lower


def scope_fields():
    return [
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organization")),
        ("owner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="+", to="identity.organizationmembership")),
    ]


def name_constraints(field, prefix):
    return [
        models.UniqueConstraint(Lower(field), models.F("organization"), condition=models.Q(owner__isnull=True), name=f"{prefix}_shared_ci"),
        models.UniqueConstraint(Lower(field), models.F("organization"), models.F("owner"), condition=models.Q(owner__isnull=False), name=f"{prefix}_personal_ci"),
    ]


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0031_participant_data"),
        ("identity", "0042_organization_participant_limit"),
    ]
    operations = [
        migrations.CreateModel(
            name="ReplyTemplateCategory",
            fields=[*scope_fields(), ("name", models.CharField(max_length=120))],
            options={"ordering": ["name", "id"], "constraints": name_constraints("name", "template_category")},
        ),
        migrations.CreateModel(
            name="ReplyTemplateTag",
            fields=[*scope_fields(), ("name", models.CharField(max_length=120))],
            options={"ordering": ["name", "id"], "constraints": name_constraints("name", "template_tag")},
        ),
        migrations.CreateModel(
            name="ReplyTemplateManagementGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organization")),
                ("membership", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="reply_template_management_grant", to="identity.organizationmembership")),
            ],
            options={"abstract": False},
        ),
        migrations.AddField(
            model_name="replytemplate", name="owner", field=scope_fields()[2][1],
        ),
        migrations.AddField(
            model_name="replytemplate", name="category",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="templates", to="conversations.replytemplatecategory"),
        ),
        migrations.RemoveConstraint(model_name="replytemplate", name="uniq_reply_template_org_title_ci"),
        *[migrations.AddConstraint(model_name="replytemplate", constraint=constraint)
          for constraint in name_constraints("title", "reply_template")],
        migrations.CreateModel(
            name="ReplyTemplateTagLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organization")),
                ("tag", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="conversations.replytemplatetag")),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="conversations.replytemplate")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("template", "tag"), name="uniq_reply_template_tag")]},
        ),
        migrations.AddField(
            model_name="replytemplate", name="tags",
            field=models.ManyToManyField(through="conversations.ReplyTemplateTagLink", to="conversations.replytemplatetag"),
        ),
    ]
