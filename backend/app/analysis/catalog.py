"""What data exists: overall coverage and the stations near a point."""
import pandas as pd

from ..data.repositories import ReferenceRepository, SensorRepository
from .constants import DAY_DEFINITION, REFERENCE, SENSOR, UNIT
from .geo import distances_km

STATION_COLUMNS = ["station", "name", "kind", "distance_km", "lat", "lon", "station_type", "area_type",
                   "data_from", "data_to"]


class Catalog:
    def __init__(self, reference: ReferenceRepository, sensors: SensorRepository | None):
        self.reference, self.sensors = reference, sensors

    def coverage(self, guideline_sets: list[str], versions: dict) -> dict:
        first, last = self.reference.date_range
        out = {
            "unit": UNIT, "day_definition": DAY_DEFINITION,
            "reference_stations": {"from": first, "to": last, "stations": len(self.reference.pm25_stations())},
            "sensors": None, "guideline_sets": guideline_sets, "versions": versions,
            "limitations": ["The ranges are the union over all stations. Individual stations can stop earlier: "
                            "use /stations for the data period near a specific location."],
        }
        if self.sensors:
            kits = self.sensors.kit_stations()
            out["sensors"] = {"from": kits["data_from"].min(), "to": kits["data_to"].max(), "stations": len(kits)}
        return out

    def stations(self, lat: float, lon: float, radius_km: float) -> dict:
        """Stations within radius_km, nearest first, with the period they have PM2.5 data."""
        frames = [self.reference.pm25_stations().assign(kind=REFERENCE)]
        if self.sensors:
            frames.append(self.sensors.kit_stations().assign(kind=SENSOR))
        df = pd.concat(frames, ignore_index=True)
        df["distance_km"] = distances_km(df, lat, lon)
        df = df[df["distance_km"] <= radius_km].sort_values("distance_km").reindex(columns=STATION_COLUMNS)
        records = df.astype(object).where(df.notna(), None).to_dict("records")
        stations = [{**{k: v for k, v in r.items() if k != "station"}, "id": r["station"],
                     "distance_km": round(float(r["distance_km"]), 2)} for r in records]
        return {"location": {"lat": lat, "lon": lon}, "radius_km": radius_km, "count": len(stations),
                "stations": stations,
                "limitations": ["data_from/data_to give the first and last day with PM2.5 data; "
                                "there can be gaps in between."]}
