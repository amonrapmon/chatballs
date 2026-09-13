"""Порталы, оставшиеся на `.localhost`, переезжают на домен установки.

До появления `addressing.help_base_domain` базовый домен приходил только из
переменной окружения, а задать её в коробке негде: у продукта нет .env. Поэтому
на реальной установке адрес портала складывался как `help.localhost` — снаружи
он не вёл никуда и сертификата не получал. Теперь домен известен из мастера
первого запуска, и такие адреса пора привести к нему.

Переписываются только суффиксы `.localhost`: ссылки, которые всё равно не
работали. Всё остальное — в том числе dev-стек и staging с явной переменной —
остаётся как есть: там смена адреса ломала бы живые ссылки на статьи.
"""

from django.db import migrations


def move_hosted_domains_to_installation(apps, schema_editor):
    from chatballs.support_portals.addressing import base_domain_for

    InstanceSettings = apps.get_model("identity", "InstanceSettings")
    host = (
        InstanceSettings.objects.filter(pk=1)
        .values_list("public_host", flat=True)
        .first()
        or ""
    )
    base_domain = base_domain_for(host)
    if not base_domain or base_domain == "localhost":
        return

    SupportPortal = apps.get_model("support_portals", "SupportPortal")
    portals = SupportPortal.objects.filter(hosted_domain__endswith=".localhost")
    for portal in portals.only("id", "slug", "hosted_domain"):
        moved = f"{portal.slug}.{base_domain}"
        taken = SupportPortal.objects.exclude(id=portal.id).filter(hosted_domain=moved)
        if taken.exists():
            continue
        SupportPortal.objects.filter(id=portal.id).update(hosted_domain=moved)


class Migration(migrations.Migration):
    dependencies = [
        ("support_portals", "0010_article_files"),
        # Домен установки живёт в настройках инстанса: без этой таблицы его
        # неоткуда прочитать.
        ("identity", "0033_instance_previous_public_host"),
    ]

    operations = [
        migrations.RunPython(
            move_hosted_domains_to_installation,
            migrations.RunPython.noop,
        ),
    ]
