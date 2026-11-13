"""The shared analysis pipeline: observations -> per-station means -> distance-weighted estimates."""
from dataclasses import dataclass
from datetime import date as Date

import pandas as pd

from . import weighting
from .audit import AuditLog
from .errors import NoDataError
from .observations import ObservationLoader
from .periods import RESOLUTIONS, period_label


@dataclass
class WeightedResult:
    per: pd.DataFrame          # kept station-period means with weight and share
    estimates: pd.DataFrame    # per (period, kind)
    chosen: pd.DataFrame       # per period: sensors where available, else reference
    r_parameters: dict


class Pipeline:
    def __init__(self, loader: ObservationLoader):
        self.loader = loader

    def run(self, audit: AuditLog, lat: float, lon: float, start: Date, end: Date, resolution: str,
            radius_km: float, cutoff: float, min_hours: int) -> WeightedResult:
        res = RESOLUTIONS[resolution]
        obs = self.loader.load(lat, lon, start, end, radius_km, cutoff, audit)

        required = res.required_hours(min_hours)
        per, excluded = weighting.drop_sparse(weighting.station_means(obs.hourly, obs.stations, res), required)
        detail = {"station_periods_used": len(per), "station_periods_excluded_for_too_few_hours": len(excluded)}
        if start == end:  # one period: say which stations were left out
            detail["excluded_for_too_few_hours"] = {s: int(h) for s, h in excluded["hours"].droplevel("period").items()}
        audit.log(f"{res.label} mean per station", **detail)
        if per.empty:
            raise NoDataError(f"No station has >= {required} valid hours for {period_label(start, end)}", audit.steps)

        per = weighting.add_weights(per)
        est = weighting.estimates(per)
        return WeightedResult(per, est, weighting.preferred(est), obs.r_parameters)
