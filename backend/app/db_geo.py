from __future__ import annotations

import math
from typing import Any, List

from shapely.geometry import Polygon, MultiPolygon
from shapely.geometry.base import BaseGeometry
from shapely import wkb as shapely_wkb
from shapely.ops import transform


def _extract_polygons(geom: BaseGeometry) -> List[Polygon]:
    """Extract all Polygons from a geometry, handling MultiPolygons and GeometryCollections."""
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    if hasattr(geom, "geoms"):
        polys = []
        for g in geom.geoms:
            polys.extend(_extract_polygons(g))
        return polys
    return []


def polygon_to_ring(p: Polygon) -> list[list[float]]:
    """Convert a Polygon's exterior to a list of [x, y] coordinates."""
    if p is None or p.is_empty or not hasattr(p, "exterior"):
        return []
    coords = list(p.exterior.coords)
    if not coords:
        return []
    # Ensure closed ring
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return [[float(x), float(y)] for x, y in coords]


def geometry_to_rings(geom: BaseGeometry) -> list[list[list[float]]]:
    """Convert any geometry to a list of polygon rings (list of list of [x,y])."""
    polys = _extract_polygons(geom)
    return [polygon_to_ring(p) for p in polys if not p.is_empty]


def transform_3857_to_4326(geom: BaseGeometry) -> BaseGeometry:
    """Project EPSG:3857 (meters) to EPSG:4326 (lat/lon) using spherical mercator inverse."""
    if geom is None or geom.is_empty:
        return geom
    def project(x, y, z=None):
        lon = (x * 180.0) / 20037508.34
        lat = (math.atan(math.exp(y * math.pi / 20037508.34)) * 360.0 / math.pi) - 90.0
        return (lon, lat)

    return transform(project, geom)
