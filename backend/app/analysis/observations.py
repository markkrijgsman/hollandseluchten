"""Step 1 of every analysis: pick nearby stations and run the Analyse-Together R functions over their hourly rows."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date

import pandas as pd

from ..data.repositories import ReferenceRepository, SensorRepository
from ..integrations.r_bridge import run_r_analysis
from ..settings import Settings
from .audit import AuditLog, RFunctionsStep, SelectStationsStep
from .constants import REFERENCE, SENSOR, SENSOR_PREFIX
from .errors import NoDataError
from .facts import load_facts
from .geo import distances_km
from .periods import period_label


@dataclass
class Observations:
    stations: pd.DataFrame     # one row per station (index: station): name, kind, distance_km, station_type
    hourly: pd.DataFrame       # cleaned hourly rows: station, parameter, value, date, sd
    r_parameters: dict         # parameters the R functions reported using
    facts: dict = None         # load_facts(): what the R functions did


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
            raise NoDataError(f"No PM2.5 data within {radius_km} km for {period_label(start, end)}", audit.as_dicts())
        data = pd.concat(frames, ignore_index=True)

        rows = [{"station": r.station, "parameter": r.parameter, "value": float(r.value), "date": r.hour}
                for r in data.itertuples()]
        r_out = run_r_analysis(rows, cutoff, self.settings.analyse_together_dir, self.settings.rscript)
        # functions and parameters are reported by R itself, so the audit shows what actually ran
        facts = load_facts(len(rows), r_out["removed_outliers"], r_out["parameters"], self.sensors is not None)
        audit.log(RFunctionsStep(functions=r_out["functions"], parameters=r_out["parameters"],
                                 hourly_values_in=facts["hourly_values_in"], outliers_removed=facts["outliers_removed"]))
        if not r_out["rows"]:
            raise NoDataError("All values were removed as outliers", audit.as_dicts())
        # only official stations have a station type (the sensor kits' metadata has none)
        stations = (data.rename(columns={"stationstype": "station_type"}).drop_duplicates("station")
                    .set_index("station").reindex(columns=["name", "kind", "distance_km", "station_type"]))
        return Observations(stations, pd.DataFrame(r_out["rows"]), r_out["parameters"], facts)

    def _reference(self, lat, lon, start, end, radius_km, audit: AuditLog) -> pd.DataFrame:
        ref = nearby(self.reference.hourly_range(start, end), lat, lon, radius_km)
        audit.log(SelectStationsStep(
            action="select reference stations", kind=REFERENCE, source="Luchtmeetnet",
            stations=sorted(ref["station"].unique().tolist()),
            station_types=ref.drop_duplicates("station").set_index("station")["stationstype"].dropna().sort_index().to_dict(),
            note="official stations; PM2.5 hourly values"))
        return ref.assign(parameter="pm25", kind=REFERENCE)

    def _sensors(self, lat, lon, start, end, radius_km, audit: AuditLog) -> pd.DataFrame | None:
        if self.sensors is None:
            audit.log(SelectStationsStep(
                action="select Hollandse Luchten sensors", kind=SENSOR, skipped=True,
                reason="no sensor data configured (HL_SENSOR_PARQUET)"))
            return None
        sens = nearby(self.sensors.hourly_range(start, end), lat, lon, radius_km)
        sens["station"] = SENSOR_PREFIX + sens["station"].astype(str)
        audit.log(SelectStationsStep(
            action="select Hollandse Luchten sensors", kind=SENSOR, source="Hollandse Luchten",
            stations=sorted(sens["station"].str.removeprefix(SENSOR_PREFIX).unique().tolist()),
            note="calibrated PM2.5 (pm25_kal), hourly mean"))
        return sens.assign(parameter="pm25_kal", kind=SENSOR)
