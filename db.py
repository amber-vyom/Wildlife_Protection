"""SQLite setup, helpers and demo seed data."""
import hashlib
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "wildlife.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL, role TEXT NOT NULL,
    is_active INTEGER DEFAULT 1, skills TEXT DEFAULT '', contact TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS incident_report(
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_time TEXT NOT NULL, location TEXT NOT NULL,
    description TEXT NOT NULL, status TEXT DEFAULT 'Open');
CREATE TABLE IF NOT EXISTS rescue_case(
    case_id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES incident_report,
    agent_id INTEGER REFERENCES users,
    status TEXT DEFAULT 'Reported', assigned_date TEXT,
    location TEXT, notes TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS enclosure(
    enclosure_id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT, capacity INTEGER NOT NULL, location TEXT,
    quarantine INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS animal(
    animal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER REFERENCES rescue_case,
    species TEXT NOT NULL, age INTEGER, gender TEXT,
    current_status TEXT DEFAULT 'Admitted',
    enclosure_id INTEGER REFERENCES enclosure, intake_date TEXT);
CREATE TABLE IF NOT EXISTS medical_record(
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id INTEGER NOT NULL REFERENCES animal, vet_id INTEGER,
    date TEXT, diagnosis TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS treatment_plan(
    plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id INTEGER NOT NULL REFERENCES animal, vet_id INTEGER,
    medication TEXT, schedule TEXT, start_date TEXT, end_date TEXT,
    status TEXT DEFAULT 'Active');
CREATE TABLE IF NOT EXISTS health_log(
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id INTEGER NOT NULL REFERENCES animal, caretaker_id INTEGER,
    date TEXT, weight REAL, temperature REAL, behaviour TEXT,
    feeding TEXT, remarks TEXT);
CREATE TABLE IF NOT EXISTS release_record(
    release_id INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id INTEGER NOT NULL REFERENCES animal, vet_id INTEGER,
    assessment_date TEXT, ready INTEGER DEFAULT 0, permit_no TEXT,
    release_date TEXT, outcome TEXT, location TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS volunteer_task(
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    volunteer_id INTEGER NOT NULL REFERENCES users,
    description TEXT, shift TEXT, status TEXT DEFAULT 'Assigned');
CREATE TABLE IF NOT EXISTS supply_item(
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, type TEXT, quantity INTEGER, unit TEXT,
    expiry_date TEXT, min_level INTEGER DEFAULT 5);
CREATE TABLE IF NOT EXISTS equipment(
    equipment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, type TEXT, status TEXT DEFAULT 'Available',
    location TEXT, last_maintenance TEXT);
CREATE TABLE IF NOT EXISTS donation(
    donation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_id INTEGER NOT NULL REFERENCES users, date TEXT,
    amount REAL, type TEXT, purpose TEXT, status TEXT DEFAULT 'Received');
"""

DEMO_USERS = [
    ("Chitra Coordinator", "coordinator@wild.org", "coord123", "Coordinator"),
    ("Farhan Agent", "agent@wild.org", "agent123", "Field Agent"),
    ("Dr. Vera Vet", "vet@wild.org", "vet123", "Veterinarian"),
    ("Carl Caretaker", "caretaker@wild.org", "care123", "Caretaker"),
    ("Vik Volunteer", "volunteer@wild.org", "vol123", "Volunteer"),
    ("Dana Donor", "donor@wild.org", "donor123", "Donor"),
]


def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def q(sql: str, params=()) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def x(sql: str, params=()) -> int:
    """Execute a write; return last row id."""
    with conn() as c:
        return c.execute(sql, params).lastrowid


def init_db() -> None:
    with conn() as c:
        c.executescript(SCHEMA)
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            for name, email, pw, role in DEMO_USERS:
                c.execute(
                    "INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)",
                    (name, email, hash_pw(pw), role))
            c.executemany(
                "INSERT INTO enclosure(type,capacity,location,quarantine) VALUES(?,?,?,?)",
                [("Aviary", 4, "Block A", 0), ("Large mammal pen", 2, "Block B", 0),
                 ("Reptile house", 6, "Block C", 0), ("Quarantine ward", 3, "Clinic", 1)])
            c.executemany(
                "INSERT INTO supply_item(name,type,quantity,unit,expiry_date,min_level) VALUES(?,?,?,?,?,?)",
                [("Antibiotic (Amoxicillin)", "Medical", 20, "vials", "2027-06-30", 5),
                 ("Bandages", "Medical", 3, "rolls", "", 10),
                 ("Fruit mix", "Food", 40, "kg", "", 10)])
            c.executemany(
                "INSERT INTO equipment(name,type,status,location,last_maintenance) VALUES(?,?,?,?,?)",
                [("Rescue Van 1", "Vehicle", "Available", "Garage", "2026-08-01"),
                 ("Capture Net Set", "Tool", "Available", "Store", "")])
