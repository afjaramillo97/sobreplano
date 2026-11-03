"""Reading and writing project coordinates; the only place that knows PostGIS' (lon, lat) order."""

from geoalchemy2 import WKTElement
from sqlalchemy import Float, func

from sobreplano.domain.catalog import GeoPoint
from sobreplano.infrastructure.db.models import ProjectRow

# geoalchemy2.shape.to_shape fails pyright strict, so coordinates are read with PostGIS functions.
LAT = func.ST_Y(func.geometry(ProjectRow.location), type_=Float())
LON = func.ST_X(func.geometry(ProjectRow.location), type_=Float())


def to_wkt_point(point: GeoPoint) -> WKTElement:
    """Build the geography value to store; PostGIS takes x = longitude first, then latitude."""
    return WKTElement(f"POINT({point.lon} {point.lat})", srid=4326)


def to_geo_point(lat: float | None, lon: float | None) -> GeoPoint | None:
    """The point read with LAT and LON, or None for a project stored without location."""
    if lat is None or lon is None:
        return None
    return GeoPoint(lat=lat, lon=lon)
