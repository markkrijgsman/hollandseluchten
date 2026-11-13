"""Place/address lookup through the PDOK Locatieserver (free Dutch geocoder, no API key)."""
import os
import re

import httpx

URL = os.environ.get("HL_GEOCODER_URL", "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free")
TYPES = "woonplaats OR gemeente OR wijk OR buurt OR adres OR weg OR postcode"
_POINT = re.compile(r"POINT\(([-\d.]+) ([-\d.]+)\)")


class GeocodeError(RuntimeError):
    pass


def geocode(query: str, limit: int = 5, timeout: float = 10.0) -> list[dict]:
    """Return up to `limit` candidates, best first. Several candidates means the query is ambiguous."""
    try:
        resp = httpx.get(URL, params={"q": query, "rows": limit, "fl": "id,weergavenaam,type,centroide_ll",
                                      "fq": f"type:({TYPES})"}, timeout=timeout)
        resp.raise_for_status()
        docs = resp.json()["response"]["docs"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise GeocodeError(f"geocoder unavailable: {exc}") from exc
    out = []
    for doc in docs:
        m = _POINT.match(doc.get("centroide_ll", ""))
        if m:  # PDOK gives POINT(lon lat)
            out.append({"name": doc["weergavenaam"], "type": doc["type"],
                        "lat": float(m.group(2)), "lon": float(m.group(1))})
    return out
