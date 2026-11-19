"""
SQLite schema for the Traffic Management System.

Original project tables are kept. `Location` is extended with coordinates and
zone metadata; `traffic_reading` is an append-only log of observed/estimated
status snapshots (used to retrain on real data once a live provider is set up).
"""
import sqlite3

from config import DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS Location (
    location_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    location_name VARCHAR(100) NOT NULL,
    road_name     VARCHAR(150) NOT NULL,
    city          VARCHAR(100) NOT NULL,
    state         VARCHAR(60)  NOT NULL,
    pincode       CHAR(6),
    latitude      REAL NOT NULL,
    longitude     REAL NOT NULL,
    zone_kind     VARCHAR(40) NOT NULL,
    population_m  REAL NOT NULL,
    UNIQUE (city, zone_kind)
);
CREATE TABLE IF NOT EXISTS Traffic_Signal (
    signal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL,
    signal_type VARCHAR(30) NOT NULL,
    signal_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    green_duration_seconds INTEGER NOT NULL DEFAULT 30,
    FOREIGN KEY (location_id) REFERENCES Location(location_id),
    CHECK (signal_status IN ('ACTIVE', 'INACTIVE', 'MAINTENANCE')),
    CHECK (green_duration_seconds > 0)
);
CREATE TABLE IF NOT EXISTS Driver (
    driver_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name VARCHAR(100) NOT NULL,
    license_number VARCHAR(30) NOT NULL UNIQUE,
    phone VARCHAR(15) UNIQUE
);
CREATE TABLE IF NOT EXISTS Vehicle (
    vehicle_id INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_id INTEGER NOT NULL,
    registration_number VARCHAR(20) NOT NULL UNIQUE,
    vehicle_type VARCHAR(30) NOT NULL,
    model VARCHAR(60),
    FOREIGN KEY (driver_id) REFERENCES Driver(driver_id)
);
CREATE TABLE IF NOT EXISTS Violation_Type (
    violation_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
    violation_name VARCHAR(100) NOT NULL UNIQUE,
    fine_amount DECIMAL(10,2) NOT NULL,
    CHECK (fine_amount >= 0)
);
CREATE TABLE IF NOT EXISTS Traffic_Officer (
    officer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name VARCHAR(100) NOT NULL,
    badge_number VARCHAR(30) NOT NULL UNIQUE,
    officer_rank VARCHAR(50) NOT NULL
);
CREATE TABLE IF NOT EXISTS Traffic_Violation (
    violation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_id INTEGER NOT NULL,
    vehicle_id INTEGER NOT NULL,
    violation_type_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    officer_id INTEGER NOT NULL,
    violation_datetime DATETIME NOT NULL,
    fine_amount DECIMAL(10,2) NOT NULL,
    payment_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    FOREIGN KEY (driver_id) REFERENCES Driver(driver_id),
    FOREIGN KEY (vehicle_id) REFERENCES Vehicle(vehicle_id),
    FOREIGN KEY (violation_type_id) REFERENCES Violation_Type(violation_type_id),
    FOREIGN KEY (location_id) REFERENCES Location(location_id),
    FOREIGN KEY (officer_id) REFERENCES Traffic_Officer(officer_id),
    CHECK (fine_amount >= 0),
    CHECK (payment_status IN ('PENDING', 'PAID', 'OVERDUE'))
);
CREATE TABLE IF NOT EXISTS traffic_reading (
    reading_id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL,
    reading_datetime DATETIME NOT NULL,          -- IST
    congestion_score REAL NOT NULL,
    congestion_level VARCHAR(20) NOT NULL,
    current_speed_kmph REAL,
    free_flow_speed_kmph REAL,
    precip_mm REAL DEFAULT 0,
    source VARCHAR(20) NOT NULL,                 -- 'tomtom' | 'ml_estimate'
    FOREIGN KEY (location_id) REFERENCES Location(location_id),
    CHECK (congestion_level IN ('Low', 'Moderate', 'Heavy', 'Severe')),
    CHECK (congestion_score >= 0 AND congestion_score <= 100)
);
CREATE INDEX IF NOT EXISTS idx_location_city ON Location(city);
CREATE INDEX IF NOT EXISTS idx_reading_loc_time ON traffic_reading(location_id, reading_datetime DESC);
CREATE INDEX IF NOT EXISTS idx_reading_time ON traffic_reading(reading_datetime DESC);
"""


def init_database():
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def seed_locations(zones):
    """Insert zones, or refresh their details if (city, zone_kind) already exists (keeps location_id stable)."""
    conn = get_connection()
    conn.executemany(
        """INSERT INTO Location
           (location_name, road_name, city, state, latitude, longitude, zone_kind, population_m)
           VALUES (:location_name, :road_name, :city, :state, :latitude, :longitude, :zone_kind, :population_m)
           ON CONFLICT(city, zone_kind) DO UPDATE SET
               location_name = excluded.location_name, road_name = excluded.road_name, state = excluded.state,
               latitude = excluded.latitude, longitude = excluded.longitude, population_m = excluded.population_m""",
        zones,
    )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM Location").fetchone()[0]
    conn.close()
    return n


def ensure_seeded():
    """
    Make sure the schema exists and the zone table matches data/zones.json. Cheap and idempotent (an upsert),
    so a fresh checkout starts with just `python app.py` - no separate setup step for the database.
    """
    from cities import build_zones
    init_database()
    seed_locations(build_zones())


def load_zones():
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("SELECT * FROM Location ORDER BY location_id")]
    conn.close()
    return rows


if __name__ == "__main__":
    init_database()
    print("Database initialised at", DB_PATH)
