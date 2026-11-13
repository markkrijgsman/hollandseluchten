"""Comparison of a daily series with reference levels (WHO, EU, ... from config/guidelines.toml)."""
from __future__ import annotations

from .models import AnnualComparison, DailyComparison, SeriesPoint


def compare_with_levels(series: list[SeriesPoint], levels: list[dict], days: int
                        ) -> tuple[list[DailyComparison | AnnualComparison], list[dict]]:
    """Return (one comparison per level, one facts dict per level for the considerations)."""
    comparisons, facts = [], []
    for level in levels:
        limit = level["limit"]
        shared = {"level_name": level["name"], "level_type": level["type"], "level_limit": limit,
                  "level_verified": level["verified"], "period_days": days, "days_with_data": len(series)}
        if level["type"] == "daily":
            above = [p for p in series if p.pm25 > limit]
            sure = sum(p.pm25 - p.uncertainty > limit for p in series)
            possible = sum(p.pm25 + p.uncertainty > limit for p in series)
            comparisons.append(DailyComparison(
                **level, days_with_data=len(series), days_above=len(above),
                share_above=round(len(above) / len(series), 3),
                # uncertainty range: sure vs possible exceedances
                days_above_even_at_lower_bound=sure, days_above_at_upper_bound=possible))
            facts.append({**shared, "ambiguous_days": possible - sure})
        else:
            mean = sum(p.pm25 for p in series) / len(series)
            uncertainty = sum(p.uncertainty for p in series) / len(series)
            uncertain = abs(mean - limit) <= uncertainty
            comparisons.append(AnnualComparison(
                **level, period_mean=round(mean, 2), uncertainty=round(uncertainty, 2),
                exceeded=mean > limit, uncertain=uncertain))
            facts.append({**shared, "period_mean": round(mean, 2), "mean_uncertainty": round(uncertainty, 2),
                          "level_uncertain": uncertain})
    return comparisons, facts
