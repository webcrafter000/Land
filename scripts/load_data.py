"""
Real Data GIS Loader for Buildable Land Analysis.
ULTRA-STABLE VERSION: Uses raw SQL batch inserts to bypass Pandas/SQLAlchemy to_sql bugs.
"""

import os
import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine, text

# TARGET LOCAL PATHS
WETLANDS_PATH = r"D:\OTHER D DRIVE\TX_geopackage_wetlands\TX_geopackage_wetlands.gpkg"
PARCELS_DIR = r"D:\OTHER D DRIVE\stratmap25-landparcels_48453_lp\shp"

def find_shp_in_dir(directory):
    if not os.path.exists(directory): return None
    for file in os.listdir(directory):
        if file.lower().endswith(".shp"):
            return os.path.join(directory, file)
    return None

def load_real_data():
    # Database URL
    db_url = "postgresql+psycopg2://postgres:postgres@localhost:5433/postgres"
    engine = create_engine(db_url)

    print("--- STARTING STABLE GIS DATA INGESTION ---")

    # 1. LOAD PARCELS
    parcel_shp = find_shp_in_dir(PARCELS_DIR)
    if parcel_shp:
        print(f"Loading Parcels: {parcel_shp}")
        try:
            gdf = gpd.read_file(parcel_shp, engine='pyogrio')
        except Exception:
            gdf = gpd.read_file(parcel_shp)

        print(f"Processing {len(gdf)} rows. Projecting to EPSG:3857...")
        gdf = gdf[gdf.geometry.notnull()].copy()
        gdf = gdf.to_crs(epsg=3857)

        print("Building Hex-Bridge...")
        # hex strings only (PostGIS conversion will happen later via ST_GeomFromWKB)
        gdf["geom_hex"] = gdf["geometry"].apply(lambda x: (x.wkb_hex if x is not None else None))
        gdf["geom_hex"] = gdf["geom_hex"].where(gdf["geom_hex"].notna(), None)

        id_col = next((c for c in gdf.columns if c.lower() in ['prop_id', 'parcel_id', 'id', 'gid']), gdf.columns[0])
        df = pd.DataFrame(gdf[[id_col, "geom_hex"]]).rename(columns={id_col: "parcel_id"})

        # Sanity check: ensure geom_hex is strictly str or None
        sample_bad = df["geom_hex"].map(lambda v: not (v is None or isinstance(v, str))).any()
        if sample_bad:
            raise ValueError("geom_hex contains non-string values; expected hex strings or NULL.")

        print(f"Uploading {len(df)} parcels as text chunks (Safe Mode)...")
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS parcels_temp"))
            connection.execute(text("CREATE TABLE parcels_temp (parcel_id TEXT, geom_hex TEXT)"))

            records = df.to_dict("records")
            batch_size = 5000
            insert_stmt = text("INSERT INTO parcels_temp (parcel_id, geom_hex) VALUES (:parcel_id, :geom_hex)")
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                connection.execute(insert_stmt, batch)
                print(f"  ...inserted {min(i + batch_size, len(records))}/{len(records)} rows")

        print("Converting text back to PostGIS geometries and indexing...")
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS parcels CASCADE"))
            conn.execute(text("""
                CREATE TABLE parcels AS
                SELECT parcel_id, ST_GeomFromWKB(decode(geom_hex, 'hex'), 3857)::geometry(Geometry, 3857) as geometry
                FROM parcels_temp
            """))
            conn.execute(text("DROP TABLE parcels_temp"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS parcels_geom_idx ON parcels USING GIST (geometry)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS parcels_id_idx ON parcels (parcel_id)"))
        print("SUCCESS: Parcels table is live.")
    else:
        print(f"ERROR: No .shp file found in {PARCELS_DIR}")

    # 2. LOAD WETLANDS
    if os.path.exists(WETLANDS_PATH):
        print(f"\nLoading Wetlands from: {WETLANDS_PATH}")
        gdf_wet = gpd.read_file(WETLANDS_PATH)
        gdf_wet = gdf_wet[gdf_wet.geometry.notnull()].copy()
        gdf_wet = gdf_wet.to_crs(epsg=3857)

        gdf_wet["geom_hex"] = gdf_wet["geometry"].apply(lambda x: (x.wkb_hex if x is not None else None))
        gdf_wet["geom_hex"] = gdf_wet["geom_hex"].where(gdf_wet["geom_hex"].notna(), None)
        df_wet = pd.DataFrame(gdf_wet[["geom_hex"]])

        # Sanity check
        sample_bad = df_wet["geom_hex"].map(lambda v: not (v is None or isinstance(v, str))).any()
        if sample_bad:
            raise ValueError("wetlands geom_hex contains non-string values; expected hex strings or NULL.")

        print("Uploading wetlands as text...")
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS wetlands_temp"))
            connection.execute(text("CREATE TABLE wetlands_temp (geom_hex TEXT)"))

            records = df_wet.to_dict("records")
            batch_size = 5000
            insert_stmt = text("INSERT INTO wetlands_temp (geom_hex) VALUES (:geom_hex)")
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                connection.execute(insert_stmt, batch)
                print(f"  ...inserted {min(i + batch_size, len(records))}/{len(records)} rows")

        print("Converting to PostGIS geometries...")
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS wetlands CASCADE"))
            conn.execute(text("""
                CREATE TABLE wetlands AS
                SELECT ST_GeomFromWKB(decode(geom_hex, 'hex'), 3857)::geometry(Geometry, 3857) as geometry
                FROM wetlands_temp
            """))
            conn.execute(text("DROP TABLE wetlands_temp"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS wetlands_geom_idx ON wetlands USING GIST (geometry)"))
        print("SUCCESS: Wetlands table is live.")

    print("\n--- INGESTION COMPLETE ---")
    print("Refresh your browser at http://localhost:5173")

if __name__ == "__main__":
    load_real_data()