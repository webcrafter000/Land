# Buildable Land Analysis

A full-stack app that takes a parcel and a few constraint layers (wetlands,
floodplain, transmission easements, building setbacks) and works out how
much of it is actually buildable — with a live map you can carve out or
restore area on by hand.

Testing screenshots:
<img width="1661" height="867" alt="Screenshot 2026-07-12 123111" src="https://github.com/user-attachments/assets/c2a99083-a5c8-48f2-9d09-59565617339e" />

<img width="1762" height="773" alt="Screenshot 2026-07-12 124839" src="https://github.com/user-attachments/assets/394cbcbf-dbb9-4f8d-a88f-dc786c64b5eb" />

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
  
Parcels A Texas county from TNRIS —

https://data.tnris.org (pick a county with a
manageable parcel count).

Wetlands USFWS National Wetlands Inventory —

https://www.fws.gov/program/national-
wetlands-inventory/wetlands-data

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
