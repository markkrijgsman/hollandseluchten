"""Step 1 of every analysis: pick nearby stations and run the Analyse-Together R functions over their hourly rows."""
from dataclasses import dataclass
from datetime import date as Date

import pandas as pd

from ..data.repositories import ReferenceRepository, SensorRepository
from ..integrations.r_bridge import run_r_analysis
from ..settings import Settings
from .audit import AuditLog
from .constants import REFERENCE, SENSOR, SENSOR_PREFIX
from .errors import NoDataError
from .geo import distances_km
from .periods import period_label


@dataclass
class Observations:
    stations: pd.DataFrame     # one row per station (index: station): name, kind, distance_km
    hourly: pd.DataFrame       # cleaned hourly rows: station, parameter, value, date, sd
    r_parameters: dict         # parameters the R functions reported using


def nearby(df: pd.DataFrame, lat: float, lon: float, radius_km: float) -> pd.DataFrame:
    """Keep rows of stations within radius_km; adds `distance_km`. A station's position is its median position."""
    if df.empty:
        return df
    positions = df.groupby("station")[["lat", "lon"]].median()
    positions["distance_km"] = distances_km(positions, lat, lon)
    keep = positions[positions["distance_km"] <= radius_km]
    return df[df["station"].isin(keep.index)].merge(keep[["distance_km"]], left_on="station", right_index=True)


class ObservationLoader:
    def __init__(self, settings: Settings, reference: ReferenceRepository, sensors: SensorRepository | None):
        self.settings, self.reference, self.sensors = settings, reference, sensors

    def load(self, lat: float, lon: float, start: Date, end: Date, radius_km: float, cutoff: float,
             audit: AuditLog) -> Observations:
        frames = [self._reference(lat, lon, start, end, radius_km, audit)]
        sensors = self._sensors(lat, lon, start, end, radius_km, audit)
        if sensors is not None:
            frames.append(sensors)
        frames = [f for f in frames if not f.empty]
        if not frames:
            raise NoDataError(f"No PM2.5 data within {radius_km} km for {period_label(start, end)}", audit.steps)
        data = pd.concat(frames, ignore_index=True)

        rows = [{"station": r.station, "parameter": r.parameter, "value": float(r.value), "date": r.hour}
                for r in data.itertuples()]
        r_out = run_r_analysis(rows, cutoff, self.settings.analyse_together_dir, self.settings.rscript)
        # functions and parameters are reported by R itself, so the audit shows what actually ran
        audit.log("R: Analyse-Together functions", functions=r_out["functions"], parameters=r_out["parameters"],
                  hourly_values_in=len(rows), outliers_removed=r_out["removed_outliers"])
        if not r_out["rows"]:
            raise NoDataError("All values were removed as outliers", audit.steps)
        return Observations(data.drop_duplicates("station").set_index("station")[["name", "kind", "distance_km"]],
                            pd.DataFrame(r_out["rows"]), r_out["parameters"])

    def _reference(self, lat, lon, start, end, radius_km, audit: AuditLog) -> pd.DataFrame:
        ref = nearby(self.reference.hourly_range(start, end), lat, lon, radius_km)
        audit.log("select reference stations", source="Luchtmeetnet",
                  stations=sorted(ref["station"].unique().tolist()), note="official stations; PM2.5 hourly values")
        return ref.assign(parameter="pm25", kind=REFERENCE)

    def _sensors(self, lat, lon, start, end, radius_km, audit: AuditLog) -> pd.DataFrame | None:
        if self.sensors is None:
            audit.log("select Hollandse Luchten sensors", skipped=True,
                      reason="no sensor data configured (HL_SENSOR_PARQUET)")
            return None
        sens = nearby(self.sensors.hourly_range(start, end), lat, lon, radius_km)
        sens["station"] = SENSOR_PREFIX + sens["station"].astype(str)
        audit.log("select Hollandse Luchten sensors", source="Hollandse Luchten",
                  sensors=sorted(sens["station"].unique().tolist()), note="calibrated PM2.5 (pm25_kal), hourly mean")
        return sens.assign(parameter="pm25_kal", kind=SENSOR)
