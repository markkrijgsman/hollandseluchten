"""Request models: one per analysis. They validate the REST query parameters and double as the LLM tool schemas."""
from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .geo import in_netherlands

MAX_RANGE_DAYS = {"day": 366, "hour": 31}


class PointRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    lat: float = Field(..., ge=-90, le=90, description="Latitude (WGS84), inside the Netherlands")
    lon: float = Field(..., ge=-180, le=180, description="Longitude (WGS84), inside the Netherlands")
    radius_km: float = Field(5.0, gt=0, le=50, description="Use stations within this distance of the point")

    @model_validator(mode="after")
    def _in_netherlands(self):
        if not in_netherlands(self.lat, self.lon):
            raise ValueError("Coordinate is outside the Netherlands")
        return self


class Pm25Request(PointRequest):
    """Distance-weighted daily mean PM2.5 at a coordinate on one day."""
    date: Date = Field(..., description="YYYY-MM-DD")
    min_hours: int = Field(18, ge=0, le=24, description="Minimum valid hours for a station to count")
    cutoff: float = Field(100.0, gt=0, description="Hourly values >= cutoff are outliers (ug/m3)")


class RangeRequest(PointRequest):
    start: Date = Field(..., alias="from", description="First day, YYYY-MM-DD, inclusive")
    end: Date = Field(..., alias="to", description="Last day, YYYY-MM-DD, inclusive")
    min_hours: int = Field(18, ge=0, le=24, description="Daily resolution: minimum valid hours for a station to count")
    cutoff: float = Field(100.0, gt=0, description="Hourly values >= cutoff are outliers (ug/m3)")

    @model_validator(mode="after")
    def _ordered(self):
        if self.end < self.start:
            raise ValueError("'to' must not be before 'from'")
        return self


class TimeseriesRequest(RangeRequest):
    """PM2.5 per day (max 366 days) or per hour (max 31 days) at a coordinate."""
    resolution: Literal["day", "hour"] = "day"

    @model_validator(mode="after")
    def _length(self):
        if (self.end - self.start).days + 1 > MAX_RANGE_DAYS[self.resolution]:
            raise ValueError(f"Range too long for resolution '{self.resolution}' (max {MAX_RANGE_DAYS[self.resolution]} days)")
        return self


class CompareRequest(RangeRequest):
    """Compare daily PM2.5 over a period (max 366 days) with reference levels (WHO or EU)."""
    against: str = Field("who", description="Name of the reference level set, e.g. 'who' or 'eu'")

    @model_validator(mode="after")
    def _length(self):
        if (self.end - self.start).days + 1 > MAX_RANGE_DAYS["day"]:
            raise ValueError(f"Range too long (max {MAX_RANGE_DAYS['day']} days)")
        return self


class StationsRequest(PointRequest):
    """List the measuring stations near a coordinate and the period they have data."""


class GeocodeRequest(BaseModel):
    """Turn a place name or address in the Netherlands into coordinates (candidates, best first)."""
    q: str = Field(..., min_length=2, description="Place name or address")
    limit: int = Field(5, ge=1, le=10)


class CoverageRequest(BaseModel):
    """Which dates and stations the data covers."""
