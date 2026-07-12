from __future__ import annotations

import math
from typing import Any, Iterable

from shapely.geometry import Polygon, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union, transform

# Approx conversion: EPSG:3857 units are meters.
# 1 Acre = 4046.8564224 square meters.
ACRE_M2 = 4046.8564224


def _ring_to_polygon(ring: Any) -> Polygon:
    """Safely convert coordinate rings to Shapely Polygons."""
    if not ring or not isinstance(ring, (list, tuple)) or len(ring) < 3:
        return Polygon()
    try:
        coords = [(float(pt[0]), float(pt[1])) for pt in ring]
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        poly = Polygon(coords)
        return poly if poly.is_valid else poly.buffer(0)
    except Exception:
        return Polygon()


def _safe_unary_union(geoms: Iterable[BaseGeometry]) -> BaseGeometry:
    """Combines geometries while filtering out invalid or empty inputs.
    Skips unary_union entirely for a single geometry — shapely 2.x's
    unary_union can throw a 'create_collection' ufunc TypeError on some
    single-item inputs, and a union of one geometry is just itself anyway."""
    try:
        valid_geoms = [g for g in geoms if isinstance(g, BaseGeometry) and not g.is_empty]
        if not valid_geoms:
            return Polygon()
        if len(valid_geoms) == 1:
            return valid_geoms[0]
        return unary_union(valid_geoms)
    except Exception as e:
        print(f"[UNION DEBUG] unary_union failed: {type(e).__name__}: {e}")
        return Polygon()


def transform_3857_to_4326(geom: BaseGeometry) -> BaseGeometry:
    """Project planar meters back to GPS coordinates for map display."""
    if geom is None or geom.is_empty:
        return geom
    def project(x, y, z=None):
        lon = (x * 180.0) / 20037508.34
        lat = (math.atan(math.exp(y * math.pi / 20037508.34)) * 360.0 / math.pi) - 90.0
        return (lon, lat)
    return transform(project, geom)


def _round_up_acres(area_m2: float) -> int:
    """Converts m^2 to acres and rounds UP to the nearest whole acre."""
    acres = area_m2 / ACRE_M2
    return int(math.ceil(acres - 1e-12))


def calculate_buildable_area_m2(
    parcel: BaseGeometry,
    carve_outs: list[BaseGeometry],
    restores: list[BaseGeometry],
) -> dict[str, Any]:
    """
    Computes parcel/carve-out/buildable areas in raw square meters (EPSG:3857),
    plus the final buildable geometry. No acre conversion here.
    """
    p_geom = parcel if isinstance(parcel, BaseGeometry) and not parcel.is_empty else Polygon()

    if p_geom.is_empty:
        return {
            "parcel_m2": 0.0,
            "carve_out_m2": 0.0,
            "buildable_m2": 0.0,
            "buildable_geometry": Polygon(),
        }

    carve_union = _safe_unary_union(carve_outs)
    restore_union = _safe_unary_union(restores)

    buildable_after_carve = p_geom.difference(carve_union)

    removed_area = p_geom.difference(buildable_after_carve)
    restore_overlap = restore_union.intersection(removed_area)
    final_buildable_geom = buildable_after_carve.union(restore_overlap)

    carve_out_m2 = p_geom.intersection(carve_union).area if not carve_union.is_empty else 0.0

    return {
        "parcel_m2": float(p_geom.area),
        "carve_out_m2": float(carve_out_m2),
        "buildable_m2": float(final_buildable_geom.area),
        "buildable_geometry": final_buildable_geom,
    }


def calculate_buildable_acreage(
    parcel: BaseGeometry,
    carve_outs: list[BaseGeometry],
    restores: list[BaseGeometry],
) -> int:
    """Convenience wrapper: buildable acreage only, rounded up."""
    res = calculate_buildable_area_m2(parcel, carve_outs, restores)
    return _round_up_acres(res["buildable_m2"])


def buildable_area(req: Any, db_constraints: list[BaseGeometry] | None = None) -> dict[str, Any]:
    """API wrapper ensuring correct units and breakdown reporting."""
    parcel_poly = _ring_to_polygon(getattr(req.parcel, "ring", []))
    manual_carve_polys = [_ring_to_polygon(getattr(p, "ring", [])) for p in getattr(req, "carve_outs", [])]
    restore_polys = [_ring_to_polygon(getattr(p, "ring", [])) for p in getattr(req, "restores", [])]

    all_carve_polys = list(manual_carve_polys)
    if db_constraints:
        all_carve_polys.extend(db_constraints)

    res = calculate_buildable_area_m2(parcel_poly, all_carve_polys, restore_polys)
    buildable_acres = _round_up_acres(res["buildable_m2"])

    buildable_geom_4326 = transform_3857_to_4326(res["buildable_geometry"])

    manual_union = _safe_unary_union(manual_carve_polys)

    # --- TEMP DEBUG: leaving in per request ---
    print(f"[AREA DEBUG] parcel_poly valid={parcel_poly.is_valid} area={parcel_poly.area} bounds={parcel_poly.bounds}")
    print(f"[AREA DEBUG] manual_carve_polys count={len(manual_carve_polys)}")
    for i, p in enumerate(manual_carve_polys):
        print(f"[AREA DEBUG] carve_poly[{i}] valid={p.is_valid} area={p.area} bounds={p.bounds} is_empty={p.is_empty} geom_type={p.geom_type}")
    print(f"[AREA DEBUG] manual_union valid={manual_union.is_valid} area={manual_union.area} empty={manual_union.is_empty}")
    manual_impact_m2 = parcel_poly.intersection(manual_union).area
    print(f"[AREA DEBUG] intersection area={manual_impact_m2}")
    # --- END TEMP DEBUG ---

    carve_union = _safe_unary_union(all_carve_polys)
    restore_union = _safe_unary_union(restore_polys)
    buildable_after_carve = parcel_poly.difference(carve_union)
    restore_overlap = restore_union.intersection(parcel_poly.difference(buildable_after_carve))

    return {
        "parcel_acres": round(parcel_poly.area / ACRE_M2, 4),
        "carve_out_acres": round(parcel_poly.intersection(carve_union).area / ACRE_M2, 4),
        "manual_carve_out_acres": round(manual_impact_m2 / ACRE_M2, 4),
        "restore_acres": round(restore_overlap.area / ACRE_M2, 4),
        "buildable_acres": buildable_acres,
        "buildable_geojson": mapping(buildable_geom_4326),
    }