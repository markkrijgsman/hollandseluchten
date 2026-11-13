"""Response model of the geocode tool (the analysis responses live in analysis/models.py)."""
from pydantic import BaseModel

from ..analysis.models import Reproducible


class Candidate(BaseModel):
    name: str
    type: str
    lat: float
    lon: float


class GeocodeResponse(Reproducible):
    source: str
    candidates: list[Candidate]
    limitations: list[str]
