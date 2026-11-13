"""The shared analysis pipeline: observations -> per-station means -> distance-weighted estimates."""
from dataclasses import dataclass
from datetime import date as Date

import pandas as pd

from . import weighting
from .audit import AuditLog, StationMeansStep
from .errors import NoDataError
from .facts import means_facts, result_facts
from .observations import ObservationLoader
from .periods import RESOLUTIONS, period_label


@dataclass
class WeightedResult:
    per: pd.DataFrame          # kept station-period means with weight and share
    estimates: pd.DataFrame    # per (period, kind)
    chosen: pd.DataFrame       # per period: sensors where available, else reference
    r_parameters: dict
    facts: dict                # what happened in this run; input for the considerations


class Pipeline:
    def __init__(self, loader: ObservationLoader):
        self.loader = loader

    def run(self, audit: AuditLog, lat: float, lon: float, start: Date, end: Date, resolution: str,
            radius_km: float, cutoff: float, min_hours: int) -> WeightedResult:
        res = RESOLUTIONS[resolution]
        obs = self.loader.load(lat, lon, start, end, radius_km, cutoff, audit)

        required = res.required_hours(min_hours)
        per, excluded = weighting.drop_sparse(weighting.station_means(obs.hourly, obs.stations, res), required)
        # one period: say which stations were left out
        left_out = ({s: int(h) for s, h in excluded["hours"].droplevel("period").items()} if start == end else None)
        means = means_facts(per, excluded, required)
        audit.log(StationMeansStep(action=f"{res.label} mean per station",
                                   station_periods_used=means["station_periods_used"],
                                   station_periods_excluded_for_too_few_hours=means["stations_excluded"],
                                   excluded_for_too_few_hours=left_out))
        if per.empty:
            raise NoDataError(f"No station has >= {required} valid hours for {period_label(start, end)}",
                              audit.as_dicts())

        per = weighting.add_weights(per)
        est = weighting.estimates(per)
        chosen = weighting.preferred(est)
        facts = {**obs.facts, **means, **result_facts(per, chosen, res, start, end)}
        return WeightedResult(per, est, chosen, obs.r_parameters, facts)
