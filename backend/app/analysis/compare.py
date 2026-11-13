"""Comparison of a daily series with reference levels (WHO, EU, ... from config/guidelines.toml)."""
from .models import AnnualComparison, DailyComparison, SeriesPoint


def compare_with_levels(series: list[SeriesPoint], levels: list[dict], days: int
                        ) -> tuple[list[DailyComparison | AnnualComparison], list[str]]:
    """Return (one comparison per level, extra limitations)."""
    comparisons, notes = [], []
    for level in levels:
        limit = level["limit"]
        if level["type"] == "daily":
            above = [p for p in series if p.pm25 > limit]
            comparisons.append(DailyComparison(
                **level, days_with_data=len(series), days_above=len(above),
                share_above=round(len(above) / len(series), 3),
                # uncertainty range: sure vs possible exceedances
                days_above_even_at_lower_bound=sum(p.pm25 - p.uncertainty > limit for p in series),
                days_above_at_upper_bound=sum(p.pm25 + p.uncertainty > limit for p in series)))
        else:
            mean = sum(p.pm25 for p in series) / len(series)
            uncertainty = sum(p.uncertainty for p in series) / len(series)
            comparisons.append(AnnualComparison(
                **level, period_mean=round(mean, 2), uncertainty=round(uncertainty, 2),
                exceeded=mean > limit, uncertain=abs(mean - limit) <= uncertainty))
            if days < 300:
                notes.append(f"'{level['name']}' is defined for a full year; your period is {days} days, "
                             "so this is only indicative.")
    return comparisons, notes
