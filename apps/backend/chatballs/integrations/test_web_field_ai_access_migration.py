"""Перенос «Видит AI» в режим доступа во всех WEB-подключениях (SPEC-0022 R-11)."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

VISIBLE_TO_ACCESS = {
    "string": "masked", "email": "masked", "phone": "masked", "url": "masked",
    "number": "open", "boolean": "open", "datetime": "open", "enum": "open",
}


def _targets(migration: str) -> list[tuple[str, str]]:
    """Остальные приложения остаются на вершине: откатывается только перенос."""
    leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
    return [node for node in leaves if node[0] != "integrations"] + [("integrations", migration)]


class WebFieldAiAccessMigrationTests(TransactionTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.migrate_from = _targets("0010_integration_runtime_revision")
        self.migrate_to = _targets("0011_web_field_ai_access")
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        Organization = old_apps.get_model("identity", "Organization")
        Integration = old_apps.get_model("integrations", "Integration")

        visible = [
            {"id": f"v{index}", "key": f"visible_{kind}", "label": kind, "type": kind,
             "ai_visible": True, "order": index}
            for index, kind in enumerate(VISIBLE_TO_ACCESS)
        ]
        hidden = [
            {"id": f"h{index}", "key": f"hidden_{kind}", "label": kind, "type": kind,
             "ai_visible": False, "order": index}
            for index, kind in enumerate(VISIBLE_TO_ACCESS)
        ]
        self.ids = {}
        for slug, fields in (("ai-access-first", visible), ("ai-access-second", hidden)):
            organization = Organization.objects.create(name=slug, slug=slug)
            self.ids[slug] = Integration.objects.create(
                organization=organization, name="Web", kind="MESSENGER", provider="WEB",
                config={"title": "Сайт", "fields": fields},
            ).pk
        # Поле без признака, подключение без схемы и чужой провайдер.
        self.ids["bare"] = Integration.objects.create(
            organization=organization, name="Bare", kind="MESSENGER", provider="WEB",
            config={"fields": [{"key": "note", "label": "Заметка", "type": "string"}]},
        ).pk
        self.ids["empty"] = Integration.objects.create(
            organization=organization, name="Empty", kind="MESSENGER", provider="WEB", config={},
        ).pk
        self.ids["telegram"] = Integration.objects.create(
            organization=organization, name="Telegram", kind="MESSENGER", provider="TELEGRAM",
            config={"fields": [{"key": "note", "type": "string", "ai_visible": True}]},
        ).pk

    def tearDown(self) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def _configs(self, state) -> dict:
        executor = MigrationExecutor(connection)
        executor.migrate(state)
        Integration = executor.loader.project_state(state).apps.get_model("integrations", "Integration")
        return {name: Integration.objects.get(pk=pk).config for name, pk in self.ids.items()}

    def test_forward_and_reverse(self) -> None:
        configs = self._configs(self.migrate_to)

        first = configs["ai-access-first"]
        self.assertEqual(first["title"], "Сайт")
        self.assertEqual([field["id"] for field in first["fields"]], [f"v{index}" for index in range(8)])
        self.assertEqual({field["type"]: field["ai_access"] for field in first["fields"]}, VISIBLE_TO_ACCESS)
        self.assertEqual(
            {field["ai_access"] for field in configs["ai-access-second"]["fields"]}, {"hidden"}
        )
        for name in ("ai-access-first", "ai-access-second"):
            self.assertFalse(any("ai_visible" in field for field in configs[name]["fields"]))
        self.assertEqual(configs["bare"]["fields"][0]["ai_access"], "hidden")
        self.assertEqual(configs["empty"], {})
        self.assertEqual(configs["telegram"]["fields"][0], {"key": "note", "type": "string", "ai_visible": True})

        reverted = self._configs(self.migrate_from)

        self.assertTrue(all(field["ai_visible"] is True for field in reverted["ai-access-first"]["fields"]))
        self.assertTrue(all(field["ai_visible"] is False for field in reverted["ai-access-second"]["fields"]))
        self.assertFalse(any("ai_access" in field for field in reverted["ai-access-first"]["fields"]))
