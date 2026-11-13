"""REST API: GET /pm25?lat=..&lon=..&date=YYYY-MM-DD"""
from datetime import date as Date
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .geo import in_netherlands
from .rbridge import RError
from .service import NoDataError, Pm25Service, Settings

app = FastAPI(title="Hollandse Luchten PM2.5 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


@lru_cache
def get_service() -> Pm25Service:
    return Pm25Service(Settings.from_env())


@app.get("/pm25")
def pm25(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    date: Date = Query(..., description="YYYY-MM-DD"),
    radius_km: float = Query(5.0, gt=0, le=50),
    min_hours: int = Query(18, ge=0, le=24, description="minimum valid hours for a station to count"),
    cutoff: float = Query(100.0, gt=0, description="values >= cutoff are treated as outliers (ug/m3)"),
    service: Pm25Service = Depends(get_service),
):
    if not in_netherlands(lat, lon):
        raise HTTPException(422, "Coordinate is outside the Netherlands")
    try:
        return service.compute(lat, lon, date, radius_km, cutoff, min_hours)
    except NoDataError as exc:
        raise HTTPException(404, {"message": str(exc), "audit": exc.audit})
    except RError as exc:
        raise HTTPException(503, str(exc))
