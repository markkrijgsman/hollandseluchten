"""Geographic helpers."""
from math import asin, cos, radians, sin, sqrt
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


NL_LAT, NL_LON = (50.7, 53.7), (3.2, 7.3)  # coarse bounding box around the Netherlands


def in_netherlands(lat: float, lon: float) -> bool:
    return NL_LAT[0] <= lat <= NL_LAT[1] and NL_LON[0] <= lon <= NL_LON[1]


def distances_km(df: "pd.DataFrame", lat: float, lon: float) -> "pd.Series":
    """Distance from (lat, lon) to each row of a frame with `lat` and `lon` columns."""
    import pandas as pd
    return pd.Series([haversine_km(lat, lon, la, lo) for la, lo in zip(df["lat"], df["lon"], strict=True)], index=df.index)
