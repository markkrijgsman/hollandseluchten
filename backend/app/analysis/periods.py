"""Aggregation periods (day / hour) and how to label a date range."""
from dataclasses import dataclass
from datetime import date as Date


@dataclass(frozen=True)
class Resolution:
    name: str
    label: str            # used in audit step names
    key_width: int        # characters of the "YYYY-MM-DDTHH" hour key that identify a period
    per_day: int          # periods per day
    fixed_min_hours: int | None  # None: the caller's min_hours applies

    def required_hours(self, min_hours: int) -> int:
        return min_hours if self.fixed_min_hours is None else self.fixed_min_hours

    def expected_periods(self, start: Date, end: Date) -> int:
        return ((end - start).days + 1) * self.per_day


RESOLUTIONS = {
    "day": Resolution("day", "daily", key_width=10, per_day=1, fixed_min_hours=None),
    "hour": Resolution("hour", "hourly", key_width=13, per_day=24, fixed_min_hours=1),
}


def period_label(start: Date, end: Date) -> str:
    return start.isoformat() if start == end else f"{start} to {end}"
