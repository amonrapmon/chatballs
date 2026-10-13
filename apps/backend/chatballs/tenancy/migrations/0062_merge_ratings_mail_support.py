"""Combine rating protections with the published mail and report graph."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0060_merge_ratings_main"),
        ("tenancy", "0061_merge_mail_support"),
    ]
    operations = []
