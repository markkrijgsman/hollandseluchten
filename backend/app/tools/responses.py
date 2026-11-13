"""Response model of the geocode tool (the analysis responses live in analysis/models.py)."""
from pydantic import BaseModel, Field

from ..analysis.models import Consideration, Reproducible


class Candidate(BaseModel):
    name: str
    type: str
    lat: float
    lon: float


class GeocodeResponse(Reproducible):
    source: str
    chosen: Candidate | None = Field(description="The geocoder's first match: the place to use when there are several")
    candidates: list[Candidate]
    considerations: list[Consideration]
    limitations: list[str]
