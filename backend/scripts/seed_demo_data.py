import os
from sqlalchemy import create_engine, text

def seed_demo_data():
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/postgres")
    engine = create_engine(db_url)
    
    with engine.begin() as conn:
        # Create extension if not exists
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        
        # Create tables
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS parcels (
                parcel_id text PRIMARY KEY,
                geometry geometry(Polygon, 3857)
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS wetlands (
                id serial PRIMARY KEY,
                geometry geometry(Polygon, 3857)
            );
        """))
        
        # Insert demo parcel (1000m x 1000m square)
        conn.execute(text("""
            INSERT INTO parcels (parcel_id, geometry)
            VALUES (
                'demo-parcel', 
                ST_GeomFromText('POLYGON((0 0, 1000 0, 1000 1000, 0 1000, 0 0))', 3857)
            )
            ON CONFLICT (parcel_id) DO UPDATE SET geometry = EXCLUDED.geometry;
        """))
        
        # Insert demo wetland (smaller square inside parcel)
        conn.execute(text("""
            TRUNCATE TABLE wetlands;
            INSERT INTO wetlands (geometry)
            VALUES (
                ST_GeomFromText('POLYGON((200 200, 800 200, 800 800, 200 800, 200 200))', 3857)
            );
        """))
        print("Demo data seeded successfully.")

if __name__ == "__main__":
    seed_demo_data()
