"""Сценарии updater'а запускают вспомогательные контейнеры, а не себя же.

У образа updater'а входная точка — сценарий ожидания запросов
(`deploy/docker/updater.Dockerfile`). Поэтому `docker run <образ> команда` не
выполняет команду: её имя уходит аргументом в тот же цикл ожидания. Так и
случилось в 1.5.0–1.6.1 — помощник установки поднимался без compose-меток,
уходил в вечный sleep и никогда не дописывал статус, а интерфейс бесконечно
показывал «установка идёт».

Тест держит свойство: каждый запуск собственного образа подменяет входную точку.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATER_DIR = REPO_ROOT / "deploy" / "updater"
SCRIPTS = ("chatballs-updater.sh", "chatballs-updater-apply.sh")


def logical_lines(text: str) -> list[str]:
    """Склеить продолжения строк: команда `docker run` занимает их десяток."""

    lines: list[str] = []
    buffer = ""
    for line in text.splitlines():
        buffer += line
        if buffer.endswith("\\"):
            buffer = buffer[:-1] + " "
            continue
        lines.append(buffer)
        buffer = ""
    if buffer:
        lines.append(buffer)
    return lines


@pytest.mark.parametrize("name", SCRIPTS)
def test_own_image_is_started_with_explicit_entrypoint(name: str) -> None:
    text = (UPDATER_DIR / name).read_text(encoding="utf-8")
    runs = [
        line
        for line in logical_lines(text)
        if "docker run" in line and "$SELF_IMAGE" in line
    ]
    assert runs, f"{name}: не найден запуск собственного образа"
    for run in runs:
        assert "--entrypoint" in run, (
            f"{name}: запуск собственного образа без --entrypoint — "
            f"команда уйдёт аргументом в цикл ожидания:\n{run}"
        )
