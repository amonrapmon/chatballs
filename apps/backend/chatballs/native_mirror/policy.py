"""Safe per-integration mode selection, without altering legacy transports.

No database schema or request handler is modified here. An absent, invalid,
or unrecognized setting MUST NOT activate the experimental mirror.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum


class MirrorMode(StrEnum):
    DISABLED = "DISABLED"
    LEGACY = "LEGACY"
    SHADOW = "SHADOW"
    ENABLED = "ENABLED"


CONFIG_KEY = "native_mirror_mode"


def mode_for_config(config: Mapping[str, object] | None) -> MirrorMode:
    if not isinstance(config, Mapping):
        return MirrorMode.LEGACY
    candidate = config.get(CONFIG_KEY)
    if not isinstance(candidate, str):
        return MirrorMode.LEGACY
    try:
        return MirrorMode(candidate)
    except ValueError:
        return MirrorMode.LEGACY
