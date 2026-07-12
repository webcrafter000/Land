from __future__ import annotations

import os
import json
from typing import Any

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely import wkb as shapely_wkb
from sqlalchemy import create_engine, text


def _get_engine() -> Any:
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@db:5432/postgres",
    )
    return create_engine(db_url, connect_args={"connect_timeout": 5})


def _load_ewkb(geom_ewkb: Any) -> BaseGeometry:
    """Normalize whatever psycopg2/SQLAlchemy hands back (memoryview, buffer,
    bytearray, hex str, or bytes) into real bytes before handing to shapely,
    since shapely 2.x's loader chokes on non-bytes types with an opaque
    'create_collection' ufunc error."""
    if isinstance(geom_ewkb, memoryview):
        raw = geom_ewkb.tobytes()
    elif isinstance(geom_ewkb, (bytearray,)):
        raw = bytes(geom_ewkb)
    elif isinstance(geom_ewkb, str):
        raw = bytes.fromhex(geom_ewkb)
    elif isinstance(geom_ewkb, bytes):
        raw = geom_ewkb
    else:
        raw = bytes(geom_ewkb)
    return shapely_wkb.loads(raw)


def _safe_union(geoms: list[BaseGeometry]) -> BaseGeometry:
    """Same single-geometry shortcut as area.py's _safe_unary_union — avoids
    shapely 2.x's unary_union throwing a 'create_collection' ufunc TypeError
    on some single-item inputs."""
    from shapely.ops import unary_union
    valid = [g for g in geoms if isinstance(g, BaseGeometry) and not g.is_empty]
    if not valid:
        return Polygon()
    if len(valid) == 1:
        return valid[0]
    try:
        return unary_union(valid)
    except Exception as e:
        print(f"[UNION DEBUG] postgis_client unary_union failed: {type(e).__name__}: {e}")
        return Polygon()


def get_parcel_rings(parcel_id: str) -> list[list[list[float]]]:
    """Return polygon rings in EPSG:3857 planar coordinates."""
    engine = _get_engine()
    sql = text("SELECT ST_AsEWKB(geometry) AS geom FROM parcels WHERE parcel_id = :pid LIMIT 1")
    try:
        with engine.connect() as conn:
            row = conn.execute(sql, {"pid": parcel_id}).mappings().first()
            if not row or row.get("geom") is None:
                return []
            g: BaseGeometry = _load_ewkb(row["geom"])
            from .db_geo import geometry_to_rings
            return geometry_to_rings(g)
    except Exception as e:
        print(f"[DB Error] get_parcel_rings: {e}")
        return []


def get_parcel_geojson_4326(parcel_id: str) -> Any:
    """Return parcel geometry as GeoJSON in EPSG:4326."""
    engine = _get_engine()
    sql = text("SELECT ST_AsGeoJSON(ST_Transform(geometry, 4326)) AS json FROM parcels WHERE parcel_id = :pid LIMIT 1")
    try:
        with engine.connect() as conn:
            row = conn.execute(sql, {"pid": parcel_id}).mappings().first()
            if not row or not row.get("json"):
                return None
            return json.loads(row["json"])
    except Exception as e:
        print(f"[DB Error] get_parcel_geojson_4326: {e}")
        return None


def get_constraint_rings(parcel_rings: list[list[list[float]]], table_name: str, buffer_m: float) -> list[list[list[float]]]:
    """Derive carve-outs from a specific constraint table with a buffer.
    Optimized to use spatial index by buffering the parcel first.
    """
    if not parcel_rings:
        return []

    engine = _get_engine()

    try:
        with engine.connect() as conn:
            table_exists = conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :t)"), {"t": table_name}).scalar()
            if not table_exists:
                return []

        polys: list[Polygon] = [Polygon(r) for r in parcel_rings if r]
        if not polys:
            return []

        unioned = _safe_union(polys)
        parcel_wkt = unioned.wkt

        sql = text(f"""
            WITH parcel AS (
              SELECT ST_GeomFromText(:parcel_wkt, 3857) AS geom,
                     ST_Buffer(ST_GeomFromText(:parcel_wkt, 3857), :buf_m) AS buffered_geom
            )
            SELECT ST_AsEWKB(
              ST_Union(
                ST_Intersection(
                  ST_Buffer(c.geometry, :buf_m),
                  parcel.geom
                )
              )
            ) AS geom
            FROM {table_name} c
            CROSS JOIN parcel
            WHERE ST_Intersects(c.geometry, parcel.buffered_geom)
        """)

        with engine.connect() as conn:
            row = conn.execute(sql, {"parcel_wkt": parcel_wkt, "buf_m": float(buffer_m)}).mappings().first()
            if not row or row.get("geom") is None:
                return []
            g = _load_ewkb(row["geom"])
            from .db_geo import geometry_to_rings
            return geometry_to_rings(g)
    except Exception as e:
        print(f"[DB Error] get_constraint_rings ({table_name}): {e}")
        return []


def get_constraint_geojson_4326(parcel_id: str, table_name: str, buffer_m: float) -> list[Any]:
    """Return buffered constraints as GeoJSON in EPSG:4326."""
    engine = _get_engine()
    try:
        with engine.connect() as conn:
            table_exists = conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :t)"), {"t": table_name}).scalar()
            if not table_exists:
                return []

        sql = text(f"""
            WITH p AS (SELECT geometry FROM parcels WHERE parcel_id = :pid)
            SELECT ST_AsGeoJSON(ST_Transform(ST_Intersection(ST_Buffer(c.geometry, :buf), p.geometry), 4326)) as json
            FROM {table_name} c, p
            WHERE ST_Intersects(c.geometry, ST_Buffer(p.geometry, :buf))
        """)
        with engine.connect() as conn:
            rows = conn.execute(sql, {"pid": parcel_id, "buf": buffer_m}).mappings().all()
            return [json.loads(r["json"]) for r in rows if r.get("json")]
    except Exception as e:
        print(f"[DB Error] get_constraint_geojson_4326 ({table_name}): {e}")
        return []