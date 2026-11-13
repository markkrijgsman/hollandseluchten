import pytest
from fastapi.testclient import TestClient

from app.analysis.service import Pm25Service
from app.main import app, get_service
from app.settings import Settings
from helpers import AT_DIR, REAL_DATA, r_available, write_reference, write_sensors


def pytest_collection_modifyitems(items):
    skip_real = pytest.mark.skip(reason="needs the HackathonHollandseLuchten data folder (HL_DATA_DIR)")
    for item in items:
        if "real_data" in item.keywords and not (REAL_DATA / "reference_measurements.parquet").exists():
            item.add_marker(skip_real)


@pytest.fixture(scope="session")
def reference_files(tmp_path_factory):
    return write_reference(tmp_path_factory.mktemp("reference"))


@pytest.fixture(scope="session")
def requires_r():
    """Analysis tests run the real Analyse-Together R functions; skip them where R or the checkout is missing."""
    if not r_available():
        pytest.skip("needs Rscript and a checkout of Analyse-Together (HL_ANALYSE_TOGETHER_DIR)")


@pytest.fixture
def make_service(reference_files, requires_r):
    measurements, metadata = reference_files

    def factory(sensor_path=None) -> Pm25Service:
        return Pm25Service(Settings(measurements, metadata, AT_DIR, sensor_path))
    return factory


@pytest.fixture
def make_client(make_service):
    def factory(sensor_path=None) -> TestClient:
        service = make_service(sensor_path)
        app.dependency_overrides[get_service] = lambda: service
        return TestClient(app)
    yield factory
    app.dependency_overrides.clear()


@pytest.fixture
def sensor_parquet(tmp_path):
    """Kit A ~1 km away constant 20; kit B ~2 km away constant 10 with one 500 outlier (hour 0)."""
    def flat(v):
        return [v] * 24

    return write_sensors(tmp_path / "data_sensors.parquet", {
        "A": (0.009, flat(20.0), flat(0.0)), "B": (0.018, [500.0] + [10.0] * 23, flat(0.0))})
