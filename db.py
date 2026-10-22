"""SQLite setup, helpers and demo seed data."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "wildlife.db"
UPLOAD_DIR = Path(__file__).parent / "uploads"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL, salt TEXT NOT NULL, role TEXT NOT NULL,
    is_active INTEGER DEFAULT 1, phone TEXT DEFAULT '', skills TEXT DEFAULT '',
    failed_attempts INTEGER DEFAULT 0, locked_until TEXT,
    must_change_pw INTEGER DEFAULT 0, created_at TEXT, last_login TEXT);
CREATE TABLE IF NOT EXISTS incident_report(
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracking_code TEXT UNIQUE NOT NULL,
    date_time TEXT NOT NULL, location TEXT NOT NULL, lat REAL, lon REAL,
    species TEXT, description TEXT NOT NULL, priority TEXT DEFAULT 'Medium',
    photo TEXT, status TEXT DEFAULT 'Open');
CREATE TABLE IF NOT EXISTS rescue_case(
    case_id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES incident_report,
    agent_id INTEGER REFERENCES users,
    status TEXT DEFAULT 'Reported', assigned_date TEXT, notes TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS enclosure(
    enclosure_id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT, capacity INTEGER NOT NULL, location TEXT, quarantine INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS animal(
    animal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER REFERENCES rescue_case,
    species TEXT NOT NULL, age INTEGER, gender TEXT, tag_id TEXT DEFAULT '',
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
CREATE TABLE IF NOT EXISTS surgery(
    surgery_id INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id INTEGER NOT NULL REFERENCES animal, vet_id INTEGER,
    scheduled_at TEXT, procedure TEXT, status TEXT DEFAULT 'Scheduled', notes TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS health_log(
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id INTEGER NOT NULL REFERENCES animal, caretaker_id INTEGER,
    date TEXT, weight REAL, temperature REAL, behaviour TEXT, feeding TEXT, remarks TEXT);
CREATE TABLE IF NOT EXISTS feeding(
    feed_id INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id INTEGER NOT NULL REFERENCES animal,
    meal_time TEXT, food TEXT, quantity TEXT, last_fed TEXT);
CREATE TABLE IF NOT EXISTS release_record(
    release_id INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id INTEGER NOT NULL REFERENCES animal, vet_id INTEGER,
    assessment_date TEXT, ready INTEGER DEFAULT 0, permit_no TEXT,
    release_date TEXT, outcome TEXT, location TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS tracking(
    track_id INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id INTEGER NOT NULL REFERENCES animal,
    date TEXT, lat REAL, lon REAL, notes TEXT);
CREATE TABLE IF NOT EXISTS volunteer_task(
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    volunteer_id INTEGER NOT NULL REFERENCES users,
    description TEXT, shift TEXT, status TEXT DEFAULT 'Assigned');
CREATE TABLE IF NOT EXISTS attendance(
    att_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users, check_in TEXT, check_out TEXT);
CREATE TABLE IF NOT EXISTS training(
    training_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users,
    title TEXT, completed_on TEXT, expires_on TEXT);
CREATE TABLE IF NOT EXISTS supply_item(
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, type TEXT, quantity INTEGER, unit TEXT, expiry_date TEXT, min_level INTEGER DEFAULT 5);
CREATE TABLE IF NOT EXISTS equipment(
    equipment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, type TEXT, status TEXT DEFAULT 'Available', location TEXT, last_maintenance TEXT);
CREATE TABLE IF NOT EXISTS donation(
    donation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_no TEXT, donor_id INTEGER NOT NULL REFERENCES users, date TEXT,
    amount REAL, type TEXT, purpose TEXT, status TEXT DEFAULT 'Received');
CREATE TABLE IF NOT EXISTS notification(
    notif_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users, message TEXT, created_at TEXT, is_read INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS audit_log(
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, user_id INTEGER, action TEXT, detail TEXT);
"""

# (name, email, password, role) - passwords meet the app's password policy
DEMO_USERS = [
    ("Chitra Coordinator", "coordinator@wild.org", "Coord@123", "Coordinator"),
    ("Farhan Agent", "agent@wild.org", "Agent@123", "Field Agent"),
    ("Dr. Vera Vet", "vet@wild.org", "Vet@1234", "Veterinarian"),
    ("Carl Caretaker", "caretaker@wild.org", "Care@123", "Caretaker"),
    ("Vik Volunteer", "volunteer@wild.org", "Volun@123", "Volunteer"),
    ("Dana Donor", "donor@wild.org", "Donor@123", "Donor"),
]


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
    from auth import make_credentials  # local import: auth imports db
    from datetime import datetime
    UPLOAD_DIR.mkdir(exist_ok=True)
    c = conn()
    try:
        cols = [r[1] for r in c.execute("PRAGMA table_info(users)")]
        if cols and "salt" not in cols:  # old demo schema -> rebuild
            for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                  "AND name NOT LIKE 'sqlite_%'").fetchall():
                c.execute(f"DROP TABLE {t}")
        c.executescript(SCHEMA)
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            for name, email, pw, role in DEMO_USERS:
                h, s = make_credentials(pw)
                c.execute("INSERT INTO users(name,email,password_hash,salt,role,created_at) "
                          "VALUES(?,?,?,?,?,?)", (name, email, h, s, role, ts))
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
            for code, loc, lat, lon, sp, desc, pr in [
                ("DEMO0001", "Katpadi road, Vellore", 12.9716, 79.1370, "Peacock",
                 "Peacock with injured leg near the road", "High"),
                ("DEMO0002", "VIT campus lake", 12.9692, 79.1559, "Monitor lizard",
                 "Large lizard tangled in fishing net", "Medium")]:
                rid = c.execute("INSERT INTO incident_report(tracking_code,date_time,location,lat,lon,"
                                "species,description,priority) VALUES(?,?,?,?,?,?,?,?)",
                                (code, ts, loc, lat, lon, sp, desc, pr)).lastrowid
                c.execute("INSERT INTO rescue_case(report_id) VALUES(?)", (rid,))
        c.commit()
    finally:
        c.close()
