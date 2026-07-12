# grading-key: HELIOS -4827

from __future__ import annotations

import json
from fastapi import HTTPException
from pydantic import BaseModel
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import unary_union

from .area import calculate_buildable_area_m2, _round_up_acres
from .postgis_client import (
    get_parcel_rings,
    get_constraint_rings,
    get_parcel_geojson_4326,
    get_constraint_geojson_4326
)
from .db_geo import transform_3857_to_4326

# grading-key: HELIOS -4827


def _safe_union(geoms: list) -> "Polygon | object":
    """Same single-geometry shortcut used in area.py / postgis_client.py —
    shapely 2.x's unary_union can throw a 'create_collection' ufunc TypeError
    on some single-item inputs, and a union of one geometry is just itself."""
    valid = [g for g in geoms if g is not None and not g.is_empty]
    if not valid:
        return Polygon()
    if len(valid) == 1:
        return valid[0]
    try:
        return unary_union(valid)
    except Exception as e:
        print(f"[UNION DEBUG] live_analyze unary_union failed: {type(e).__name__}: {e}")
        return Polygon()


def analyze_parcel(
    parcel_id: str,
    wetland_buffer_m: float = 30.0,
    flood_buffer_m: float = 0.0,
    transmission_buffer_m: float = 20.0,
    building_buffer_m: float = 5.0
) -> dict:
    """Perform multi-layer buildable analysis with configurable setbacks."""

    # 1. Fetch Parcel
    parcel_rings = get_parcel_rings(parcel_id)
    if not parcel_rings:
        return {
            "parcel_acres": 0, "carve_out_acres": 0, "restore_acres": 0, "buildable_acres": 0,
            "breakdown": {"parcel": 0, "carve_out": 0, "restore": 0, "buildable": 0},
            "parcel_geojson": None, "carve_outs_geojson": [], "buildable_geojson": None,
        }

    parcel_poly = Polygon(parcel_rings[0])

    # 2. Fetch Constraints (Buffered Intersections)
    constraints = {
        "wetlands": {"buf": wetland_buffer_m, "color": "#E74C3C"},
        "floodzones": {"buf": flood_buffer_m, "color": "#3498DB"},
        "transmission": {"buf": transmission_buffer_m, "color": "#9B59B6"},
        "buildings": {"buf": building_buffer_m, "color": "#27AE60"}
    }

    constraint_polys = []
    layer_breakdown = {}
    display_geoms = []

    for table, config in constraints.items():
        rings = get_constraint_rings(parcel_rings, table, config["buf"])
        layer_geoms = [Polygon(r) for r in rings if len(r) >= 3]

        # Calculate area removed by THIS layer specifically for breakdown
        if layer_geoms:
            union = _safe_union(layer_geoms)
            intersection = parcel_poly.intersection(union)
            layer_breakdown[table] = _round_up_acres(intersection.area)
            constraint_polys.extend(layer_geoms)

            # Fetch GeoJSON for display
            display_geoms.extend(get_constraint_geojson_4326(parcel_id, table, config["buf"]))
        else:
            layer_breakdown[table] = 0

    # 3. Final Calculation
    res = calculate_buildable_area_m2(parcel_poly, constraint_polys, [])

    parcel_acres = _round_up_acres(res["parcel_m2"])
    buildable_acres = _round_up_acres(res["buildable_m2"])
    total_excluded = _round_up_acres(res["carve_out_m2"])

    # Transform result for map
    buildable_4326 = transform_3857_to_4326(res["buildable_geometry"])

    return {
        "parcel_acres": parcel_acres,
        "carve_out_acres": total_excluded,
        "restore_acres": 0,
        "buildable_acres": buildable_acres,
        "breakdown": {
            "Total Parcel": parcel_acres,
            "Wetlands": layer_breakdown["wetlands"],
            "Floodplains": layer_breakdown["floodzones"],
            "Transmission": layer_breakdown["transmission"],
            "Buildings": layer_breakdown["buildings"],
            "Total Buildable": buildable_acres
        },
        "parcel_geojson": get_parcel_geojson_4326(parcel_id),
        "carve_outs_geojson": display_geoms,
        "buildable_geojson": mapping(buildable_4326),
    }