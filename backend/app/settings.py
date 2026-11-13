"""Runtime settings: where the data, the Analyse-Together checkout and R live (overridable by environment)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent  # .../hollandseluchten/backend


@dataclass
class Settings:
    reference_measurements: Path
    reference_metadata: Path
    analyse_together_dir: Path
    sensor_parquet: Path | None = None
    rscript: str = "Rscript"

    @classmethod
    def from_env(cls) -> "Settings":
        data = Path(os.environ.get("HL_DATA_DIR", BACKEND_DIR.parent / "HackathonHollandseLuchten" / "data"))
        sensors = os.environ.get("HL_SENSOR_PARQUET")
        return cls(
            reference_measurements=data / "reference_measurements.parquet",
            reference_metadata=data / "reference_station_metadata.csv",
            analyse_together_dir=Path(os.environ.get("HL_ANALYSE_TOGETHER_DIR", BACKEND_DIR.parent.parent / "Analyse-Together")),
            sensor_parquet=Path(sensors) if sensors else None,
            rscript=os.environ.get("HL_RSCRIPT", "Rscript"),
        )
