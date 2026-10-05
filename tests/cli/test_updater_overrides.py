"""Обновление применяет реальные Compose overrides к каноническому манифесту.

Проверяется только `docker compose config`: сервисы и API не запускаются.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LIBRARY = REPO_ROOT / "deploy/updater/chatballs-updater-compose.sh"
COMPOSE = REPO_ROOT / "compose.yaml"


def resolve_config(workdir: Path, config_files: list[Path]) -> subprocess.CompletedProcess:
    env = os.environ | {
        "PROJECT": "chatballs-override-check",
        "WORKDIR": str(workdir),
        "FILE": str(COMPOSE),
        "CHATBALLS_WEB_LISTENING_IP": "0.0.0.0",
    }
    return subprocess.run(
        [
            "sh", "-c",
            '. "$1"; OVERRIDE_FILES="$(updater_override_files "$2")"; '
            'compose config --format json',
            "updater-check", str(LIBRARY), ",".join(map(str, config_files)),
        ],
        env=env, capture_output=True, text=True, timeout=30,
    )


def gateway_ports(result: subprocess.CompletedProcess) -> list[dict]:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["services"]["gateway"]["ports"]


@pytest.mark.skipif(not shutil.which("docker"), reason="real Docker Compose is required")
def test_update_without_override_keeps_standard_ports(tmp_path: Path) -> None:
    ports = gateway_ports(resolve_config(tmp_path, [tmp_path / "old-compose.yaml"]))
    assert {port["published"] for port in ports} == {"80", "443"}


@pytest.mark.skipif(not shutil.which("docker"), reason="real Docker Compose is required")
def test_update_preserves_override_order_and_paths_with_spaces(tmp_path: Path) -> None:
    # Первого файла уже может не быть: его заменяет новый релиз.
    first = tmp_path / "custom ports.yaml"
    first.write_text(
        "services:\n"
        "  gateway:\n"
        "    environment:\n"
        "      CHATBALLS_PLATFORM_DOMAIN: platform.pmk-mebel.ru\n"
        "    ports: !override\n"
        '      - "127.0.0.1:18080:80"\n',
        encoding="utf-8",
    )
    extra_dir = tmp_path / "outside installation"
    extra_dir.mkdir()
    last = extra_dir / "production.yaml"
    last.write_text(
        'services:\n  gateway:\n    ports: !override\n      - "127.0.0.1:8443:80"\n',
        encoding="utf-8",
    )
    result = resolve_config(tmp_path, [tmp_path / "old-compose.yaml", first, last])
    ports = gateway_ports(result)
    assert len(ports) == 1
    assert ports[0]["host_ip"] == "127.0.0.1"
    assert ports[0]["published"] == "8443"
    assert ports[0]["target"] == 80
    gateway = json.loads(result.stdout)["services"]["gateway"]
    assert gateway["environment"]["CHATBALLS_PLATFORM_DOMAIN"] == "platform.pmk-mebel.ru"


def test_missing_active_override_fails_without_falling_back(tmp_path: Path) -> None:
    missing = tmp_path / "compose.override.yaml"
    result = resolve_config(tmp_path, [COMPOSE, missing])
    assert result.returncode != 0
    assert str(missing) in result.stderr
    assert "missing or unreadable" in result.stderr
    assert result.stdout == ""


@pytest.mark.skipif(not shutil.which("docker"), reason="real Docker Compose is required")
def test_update_uses_installation_environment_and_relative_env_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("PUBLIC_PORT=8443\n", encoding="utf-8")
    (tmp_path / "gateway.env").write_text(
        "CHATBALLS_PLATFORM_DOMAIN=platform.pmk-mebel.ru\n", encoding="utf-8",
    )
    override = tmp_path / "compose.override.yaml"
    override.write_text(
        "services:\n"
        "  gateway:\n"
        "    environment:\n"
        "      CHATBALLS_PLATFORM_DOMAIN: !reset null\n"
        "    env_file: gateway.env\n"
        "    ports: !override\n"
        '      - "127.0.0.1:${PUBLIC_PORT}:80"\n',
        encoding="utf-8",
    )
    result = resolve_config(tmp_path, [COMPOSE, override])
    ports = gateway_ports(result)
    assert ports[0]["published"] == "8443"
    gateway = json.loads(result.stdout)["services"]["gateway"]
    assert gateway["environment"]["CHATBALLS_PLATFORM_DOMAIN"] == "platform.pmk-mebel.ru"
