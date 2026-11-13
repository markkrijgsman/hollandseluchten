"""Distance-weighted means: the one place where station values are combined.

Pure pandas functions. `per` frames have index (period, station) and columns hours, mean, sd, name, kind,
distance_km (plus weight and share once `add_weights` has run).
"""
import pandas as pd

from .constants import MIN_DISTANCE_KM, SENSOR, SENSOR_PREFIX
from .models import StationEstimate
from .periods import Resolution


def station_means(hourly: pd.DataFrame, stations: pd.DataFrame, resolution: Resolution) -> pd.DataFrame:
    """Mean value and mean uncertainty per station and period, with the station's name, kind and distance."""
    keyed = hourly.assign(period=hourly["date"].str[:resolution.key_width])
    per = keyed.groupby(["period", "station"]).agg(hours=("value", "size"), mean=("value", "mean"), sd=("sd", "mean"))
    return per.join(stations, on="station")


def drop_sparse(per: pd.DataFrame, required_hours: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split into (stations with enough valid hours, stations without)."""
    enough = per["hours"] >= required_hours
    return per[enough], per[~enough]


def add_weights(per: pd.DataFrame) -> pd.DataFrame:
    """weight = 1/max(d, MIN_DISTANCE_KM)^2; share = weight / sum of weights of the same period and kind."""
    out = per.copy()
    out["weight"] = 1.0 / out["distance_km"].clip(lower=MIN_DISTANCE_KM) ** 2
    out["share"] = out["weight"] / out.groupby(["period", "kind"])["weight"].transform("sum")
    return out


def estimates(per: pd.DataFrame) -> pd.DataFrame:
    """Weighted mean value and uncertainty per (period, kind).

    Uncertainty is the weighted mean of the stations' uncertainties: errors are treated as fully correlated,
    which is conservative (averaging does not reduce it).
    """
    parts = pd.DataFrame({"pm25": per["mean"] * per["share"], "uncertainty": per["sd"] * per["share"],
                          "stations": 1}, index=per.index)
    return parts.groupby([per.index.get_level_values("period"), per["kind"]]).sum()


def preferred(est: pd.DataFrame) -> pd.DataFrame:
    """One row per period: the sensor estimate where sensors have data, otherwise the reference estimate."""
    flat = est.reset_index()
    flat["is_reference"] = flat["kind"] != SENSOR
    return (flat.sort_values(["period", "is_reference"]).drop_duplicates("period")
            .set_index("period").drop(columns="is_reference"))


def station_breakdown(per_kind: pd.DataFrame) -> list[StationEstimate]:
    """Per-station details of one (period, kind) group, nearest first."""
    rows = per_kind.reset_index().sort_values("distance_km")
    return [StationEstimate(id=r.station.removeprefix(SENSOR_PREFIX), name=r.name,
                            distance_km=round(float(r.distance_km), 2), weight=round(float(r.share), 3),
                            daily_mean=round(float(r.mean), 2), uncertainty=round(float(r.sd), 2),
                            valid_hours=int(r.hours))
            for r in rows.itertuples()]
