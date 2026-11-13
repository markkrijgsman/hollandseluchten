"""Smoke tests on the real hackathon data. Skipped when the data folder is not available."""
import pytest

from app.analysis.service import Pm25Service
from app.settings import Settings
from helpers import AT_DIR, DAY, LAT, LON, REAL_DATA, r_available

pytestmark = [pytest.mark.real_data,
              pytest.mark.skipif(not r_available(), reason="needs Rscript and Analyse-Together")]


@pytest.fixture(scope="module")
def service():
    return Pm25Service(Settings(REAL_DATA / "reference_measurements.parquet",
                                REAL_DATA / "reference_station_metadata.csv", AT_DIR))


def test_amsterdam_reference_estimate_is_plausible(service):
    body = service.compute(LAT, LON, DAY).model_dump()
    assert body["basis"] == "reference_stations" and body["uncertainty"] == 0
    assert 5 < body["pm25"] < 40 and len(body["reference"]["stations"]) >= 3


def test_coverage_and_nearby_stations(service):
    cov = service.coverage()
    assert cov.reference_stations.from_ <= "2025-05-01" <= cov.reference_stations.to
    assert "NL49017" in {s.id for s in service.stations(LAT, LON, 3).stations}  # Amsterdam-Stadhouderskade
