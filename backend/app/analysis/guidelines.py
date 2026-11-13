"""Air-quality reference levels for /pm25/compare, read from config/guidelines.toml."""
from __future__ import annotations

import os
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "config" / "guidelines.toml"
REQUIRED = {"id", "name", "type", "limit", "source", "verified"}


def load_guidelines(path: Path | None = None) -> dict[str, list[dict]]:
    path = path or Path(os.environ.get("HL_GUIDELINES_FILE", DEFAULT_FILE))
    with open(path, "rb") as fh:
        levels = tomllib.load(fh).get("levels", {})
    for group, items in levels.items():
        for item in items:
            missing = REQUIRED - item.keys()
            if missing or item["type"] not in ("daily", "annual"):
                raise ValueError(f"{path}: invalid level in '{group}': {item.get('id')} (missing {sorted(missing)})")
    return levels
