"""Which code and data a result was computed with. Informational only: nothing keys on it."""
from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from ..data.repositories import ReferenceRepository, SensorRepository
from ..settings import Settings


def file_info(path: Path, date_range: tuple[str, str] | None = None) -> dict:
    st = path.stat()
    info = {"file": path.name, "size_bytes": st.st_size,
            "modified": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(timespec="seconds")}
    if date_range:
        info["covers"] = {"from": date_range[0], "to": date_range[1]}
    return info


def git_commit(directory: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(directory), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def collect_versions(settings: Settings, reference: ReferenceRepository, sensors: SensorRepository | None) -> dict:
    return {
        "analyse_together_commit": git_commit(settings.analyse_together_dir),
        "reference_data": file_info(settings.reference_measurements, reference.date_range),
        "sensor_data": file_info(settings.sensor_parquet, sensors.date_range) if sensors else None,
    }
