"""Request validation and response schemas. No R or data needed."""
from datetime import date

import pytest
from pydantic import ValidationError

from app.main import app
from app.tools.registry import TOOLS
from app.tools.schemas import CompareRequest, Pm25Request, TimeseriesRequest

POINT = {"lat": 52.37, "lon": 4.9}


def test_coordinate_must_be_in_the_netherlands():
    with pytest.raises(ValidationError, match="outside the Netherlands"):
        Pm25Request(lat=48.85, lon=2.35, date=date(2025, 5, 1))


@pytest.mark.parametrize("model, extra", [
    (TimeseriesRequest, {"resolution": "hour", "from": "2025-01-01", "to": "2025-03-01"}),  # > 31 days hourly
    (TimeseriesRequest, {"from": "2024-01-01", "to": "2025-05-01"}),                         # > 366 days daily
    (CompareRequest, {"from": "2024-01-01", "to": "2025-05-01"}),
    (TimeseriesRequest, {"from": "2025-05-02", "to": "2025-05-01"}),                         # reversed
])
def test_range_limits(model, extra):
    with pytest.raises(ValidationError):
        model(**POINT, **extra)


def test_aliases_from_and_to_are_used_in_the_resolved_request():
    req = TimeseriesRequest(**POINT, **{"from": "2025-05-01", "to": "2025-05-02"})
    assert req.model_dump(by_alias=True, mode="json")["from"] == "2025-05-01"


def test_every_endpoint_documents_its_response_schema():
    spec = app.openapi()
    for tool in TOOLS.values():
        if tool.path == "/chat":
            continue
        ok = spec["paths"][tool.path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert ok["$ref"].endswith(tool.response.__name__)


def test_response_models_describe_the_audit_and_reproducibility_fields():
    props = TOOLS["pm25"].response.model_json_schema()["properties"]
    assert {"pm25", "uncertainty", "basis", "limitations", "audit", "request", "reproduce"} <= set(props)
