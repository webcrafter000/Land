from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Any
import os
from sqlalchemy import create_engine, text

from .area import buildable_area, ACRE_M2
from .live_analyze import analyze_parcel


app = FastAPI(title="Buildable Land Analysis API")

@app.middleware("http")
async def log_requests(request, call_next):
    if request.url.path == "/api/buildable-area":
        try:
            body = await request.body()
            print(f"[API] Recalculating buildable area: {len(body)} bytes")
        except Exception: pass
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _safe_union(geoms: list):
    """Same single-geometry shortcut as area.py / postgis_client.py /
    live_analyze.py — shapely 2.x's unary_union can throw a
    'create_collection' ufunc TypeError on some single-item inputs."""
    from shapely.ops import unary_union
    from shapely.geometry import Polygon
    valid = [g for g in geoms if g is not None and not g.is_empty]
    if not valid:
        return Polygon()
    if len(valid) == 1:
        return valid[0]
    try:
        return unary_union(valid)
    except Exception as e:
        print(f"[UNION DEBUG] main.py unary_union failed: {type(e).__name__}: {e}")
        return Polygon()

class PolygonInput(BaseModel):
    ring: list[list[float]] = Field(..., description="Closed ring coordinates")

class BuildableAreaRequest(BaseModel):
    parcel_id: str
    parcel: PolygonInput
    # Manual user adjustments
    carve_outs: list[PolygonInput] = Field(default_factory=list)
    restores: list[PolygonInput] = Field(default_factory=list)
    wetland_buffer_m: float = 30.0
    flood_buffer_m: float = 0.0
    transmission_buffer_m: float = 20.0
    building_buffer_m: float = 5.0

class BuildableAreaResponse(BaseModel):
    parcel_acres: float
    carve_out_acres: float
    restore_acres: float
    buildable_acres: int
    breakdown: dict[str, Any]
    buildable_geojson: Any | None = None

class LiveAnalyzeResponse(BaseModel):
    parcel_acres: float
    carve_out_acres: float
    restore_acres: float
    buildable_acres: int
    breakdown: dict[str, Any]
    parcel_geojson: Any
    carve_outs_geojson: list[Any]
    buildable_geojson: Any | None = None

@app.post("/api/buildable-area", response_model=BuildableAreaResponse)
def api_buildable_area(req: BuildableAreaRequest) -> BuildableAreaResponse:
    from .postgis_client import get_constraint_rings
    from shapely.geometry import Polygon

    parcel_rings = [req.parcel.ring]
    parcel_poly = Polygon(req.parcel.ring)
    db_polys = []

    # Re-evaluate all constraint layers with the current buffers
    constraints = {
        "Wetlands": ("wetlands", req.wetland_buffer_m),
        "Floodplains": ("floodzones", req.flood_buffer_m),
        "Transmission": ("transmission", req.transmission_buffer_m),
        "Buildings": ("buildings", req.building_buffer_m)
    }

    layer_stats = {}
    for label, (table, buf) in constraints.items():
        rings = get_constraint_rings(parcel_rings, table, buf)
        geoms = [Polygon(r) for r in rings if len(r) >= 3]
        if geoms:
            intersection = parcel_poly.intersection(_safe_union(geoms))
            layer_stats[f"{label} Removed"] = round(intersection.area / ACRE_M2, 2)
            db_polys.extend(geoms)
        else:
            layer_stats[f"{label} Removed"] = 0.0

    result = buildable_area(req, db_constraints=db_polys)

    # --- TEMP DEBUG: leaving in per request ---
    print(f"[DEBUG] carve_outs received: {len(req.carve_outs)}")
    for i, c in enumerate(req.carve_outs):
        print(f"[DEBUG] carve_out[{i}] ring points: {len(c.ring)}, first pt: {c.ring[0] if c.ring else None}")
    print(f"[DEBUG] restores received: {len(req.restores)}")
    print(f"[DEBUG] parcel_poly bounds: {parcel_poly.bounds}")
    print(f"[DEBUG] manual_carve_out_acres result: {result.get('manual_carve_out_acres')}")
    print(f"[DEBUG] carve_out_acres result: {result.get('carve_out_acres')}")
    # --- END TEMP DEBUG ---

    # Merge environmental breakdown with calculation result
    full_breakdown = {
        "Gross Parcel": result["parcel_acres"],
        **layer_stats,
        "Manual Adjustments": result["manual_carve_out_acres"],
        "Total Restored": result["restore_acres"],
        "Final Buildable": result["buildable_acres"]
    }
    result["breakdown"] = full_breakdown
    return BuildableAreaResponse(**result)

@app.get("/api/live-analyze/{parcel_id}", response_model=LiveAnalyzeResponse)
def api_live_analyze(
    parcel_id: str,
    wetland_buffer_m: float = 30.0,
    flood_buffer_m: float = 0.0,
    transmission_buffer_m: float = 20.0,
    building_buffer_m: float = 5.0
) -> LiveAnalyzeResponse:
    result = analyze_parcel(parcel_id, wetland_buffer_m, flood_buffer_m, transmission_buffer_m, building_buffer_m)
    return LiveAnalyzeResponse(**result)

@app.post("/api/seed-sample-data")
def seed_data():
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/postgres")
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        for t in ["parcels", "wetlands", "floodzones", "transmission", "buildings"]:
            conn.execute(text(f"DROP TABLE IF EXISTS {t} CASCADE"))
        conn.execute(text("CREATE TABLE parcels (parcel_id TEXT PRIMARY KEY, geometry GEOMETRY(Polygon, 3857))"))
        conn.execute(text("CREATE TABLE wetlands (geometry GEOMETRY(Polygon, 3857))"))
        conn.execute(text("CREATE TABLE floodzones (geometry GEOMETRY(Polygon, 3857))"))
        conn.execute(text("CREATE TABLE transmission (geometry GEOMETRY(LineString, 3857))"))
        conn.execute(text("CREATE TABLE buildings (geometry GEOMETRY(Polygon, 3857))"))
        x, y = -10880000, 3540000
        conn.execute(text("INSERT INTO parcels VALUES ('0', ST_GeomFromText(:w, 3857))"), {"w": f"POLYGON(({x} {y}, {x+2000} {y}, {x+2000} {y+2000}, {x} {y+2000}, {x} {y}))"})
        conn.execute(text("INSERT INTO wetlands VALUES (ST_GeomFromText(:w, 3857))"), {"w": f"POLYGON(({x+400} {y+400}, {x+1200} {y+400}, {x+1200} {y+1000}, {x+400} {y+1000}, {x+400} {y+400}))"})
        conn.execute(text("INSERT INTO floodzones VALUES (ST_GeomFromText(:w, 3857))"), {"w": f"POLYGON(({x} {y+1500}, {x+2000} {y+1500}, {x+2000} {y+2000}, {x} {y+2000}, {x} {y+1500}))"})
    return {"message": "Seeded."}