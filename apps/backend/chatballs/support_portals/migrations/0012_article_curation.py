from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("support_portals", "0011_hosted_domains_follow_installation"),
    ]

    operations = [
        migrations.AddField(
            model_name="portalarticle",
            name="sort_order",
            field=models.PositiveIntegerField(default=1000),
        ),
        migrations.AddField(
            model_name="portalarticle",
            name="related_article_ids",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
