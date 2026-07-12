# Buildable Land Analysis

A full-stack app that takes a parcel and a few constraint layers (wetlands,
floodplain, transmission easements, building setbacks) and works out how
much of it is actually buildable — with a live map you can carve out or
restore area on by hand.

## Stack
- **Backend:** FastAPI + PostGIS + Shapely for the geometry math
- **Frontend:** React + MapLibre GL + Mapbox Draw for the interactive map

## How area is calculated
All area math runs in EPSG:3857 (Web Mercator) using a planar formula —
no reprojection to an equal-area or geodesic CRS, per the spec. Final
buildable acreage is always rounded **up** to the nearest whole acre.
The required grading-key comment sits directly above the area calculation
function in `area.py`.

## Data
- **Parcels:** TNRIS StratMap25 land parcels, Travis County (downloaded
  locally from data.tnris.org, not committed to the repo).
- **Wetlands:** USFWS National Wetlands Inventory geopackage for Texas,
  downloaded locally from fws.gov.

Both were downloaded and loaded into a local PostGIS instance while
testing — they're not bundled with the repo since they're large and
public. `scripts/load_data.py` handles the ingestion once you've
downloaded them into place (see paths at the top of the script).

## Setbacks (defaults, all configurable via the UI)
| Layer | Default buffer | Why |
|---|---|---|
| Wetlands | 30m | Common regulatory buffer used for wetland protection |
| Floodplain | 0m | FEMA 100-year floodplain treated as a hard boundary, not buffered |
| Transmission lines | 20m | Typical utility easement width |
| Buildings | 5m | Reasonable minimum structural setback |

## Running it
```bash
docker compose up -d --build
```
Frontend: http://localhost:5173
Backend: http://localhost:8000

## What I'd do differently with more time
- Persist manual carve-outs/restores per parcel instead of losing them
  on refresh.
- Debounce recalculation on rapid drawing instead of firing a request
  per vertex.
- Simplify very large/complex geometries for map display at scale.
- Currently tested primarily on Travis County parcels — would want more
  edge-case testing against messier/larger real-world geometries before
  calling this production-ready.