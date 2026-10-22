"""Domain logic (the control classes + entity behaviour from the class diagram)."""
from datetime import date, datetime

from db import hash_pw, q, x

CASE_FLOW = ["Reported", "Assigned", "Captured", "At Centre", "Closed"]
ANIMAL_STATUSES = ["Admitted", "Under Treatment", "Ready for Release", "Released", "Sanctuary/Zoo"]
ROLES = ["Coordinator", "Field Agent", "Veterinarian", "Caretaker", "Volunteer", "Donor"]


class RuleError(Exception):
    """Raised when a business rule is violated; shown to the user."""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def today() -> str:
    return date.today().isoformat()


# ---- User ---------------------------------------------------------------
def login(email: str, password: str) -> dict | None:
    rows = q("SELECT * FROM users WHERE email=? AND password_hash=? AND is_active=1",
             (email.strip().lower(), hash_pw(password)))
    return rows[0] if rows else None


def register_user(name, email, password, role, skills="", contact=""):
    if q("SELECT 1 FROM users WHERE email=?", (email.strip().lower(),)):
        raise RuleError("Email already registered.")
    return x("INSERT INTO users(name,email,password_hash,role,skills,contact) VALUES(?,?,?,?,?,?)",
             (name, email.strip().lower(), hash_pw(password), role, skills, contact))


def users_by_role(role):
    return q("SELECT user_id,name,email,skills,contact FROM users WHERE role=? AND is_active=1", (role,))


# ---- IncidentController / RescueController ------------------------------
def report_incident(location, description):
    """Citizen use case: no personal data stored, only the report."""
    rid = x("INSERT INTO incident_report(date_time,location,description) VALUES(?,?,?)",
            (now(), location, description))
    cid = x("INSERT INTO rescue_case(report_id,location) VALUES(?,?)", (rid, location))
    return rid, cid


def open_cases():
    return q("""SELECT c.case_id, c.status, c.location, r.description, r.date_time,
                       u.name AS agent, c.agent_id, c.notes
                FROM rescue_case c JOIN incident_report r USING(report_id)
                LEFT JOIN users u ON u.user_id=c.agent_id ORDER BY c.case_id DESC""")


def assign_agent(case_id, agent_id):
    case = q("SELECT status FROM rescue_case WHERE case_id=?", (case_id,))[0]
    if case["status"] not in ("Reported", "Assigned"):
        raise RuleError("Only Reported/Assigned cases can be (re)assigned.")
    x("UPDATE rescue_case SET agent_id=?, status='Assigned', assigned_date=? WHERE case_id=?",
      (agent_id, today(), case_id))


def advance_case(case_id, notes=""):
    case = q("SELECT status, agent_id FROM rescue_case WHERE case_id=?", (case_id,))[0]
    i = CASE_FLOW.index(case["status"])
    if i == len(CASE_FLOW) - 1:
        raise RuleError("Case is already closed.")
    if case["status"] == "Reported":
        raise RuleError("Assign a field agent first.")
    nxt = CASE_FLOW[i + 1]
    x("UPDATE rescue_case SET status=?, notes=notes||? WHERE case_id=?",
      (nxt, f"\n[{now()}] {notes}" if notes else "", case_id))
    return nxt


# ---- Enclosure / Animal -------------------------------------------------
def enclosures():
    return q("""SELECT e.*, (SELECT COUNT(*) FROM animal a WHERE a.enclosure_id=e.enclosure_id
                 AND a.current_status NOT IN ('Released','Sanctuary/Zoo')) AS occupancy
                FROM enclosure e""")


def add_enclosure(type_, capacity, location, quarantine):
    return x("INSERT INTO enclosure(type,capacity,location,quarantine) VALUES(?,?,?,?)",
             (type_, capacity, location, int(quarantine)))


def _check_capacity(enclosure_id):
    e = [e for e in enclosures() if e["enclosure_id"] == enclosure_id][0]
    if e["occupancy"] >= e["capacity"]:
        raise RuleError(f"Enclosure #{enclosure_id} is full ({e['occupancy']}/{e['capacity']}).")


def register_animal(species, age, gender, enclosure_id, case_id=None):
    _check_capacity(enclosure_id)
    aid = x("""INSERT INTO animal(case_id,species,age,gender,enclosure_id,intake_date)
               VALUES(?,?,?,?,?,?)""", (case_id, species, age, gender, enclosure_id, today()))
    if case_id:
        x("UPDATE rescue_case SET status='Closed' WHERE case_id=?", (case_id,))
    return aid


def animals(status_not_in=()):
    sql = """SELECT a.*, e.type AS enclosure FROM animal a
             LEFT JOIN enclosure e USING(enclosure_id)"""
    rows = q(sql + " ORDER BY a.animal_id DESC")
    return [r for r in rows if r["current_status"] not in status_not_in]


def assign_enclosure(animal_id, enclosure_id):
    _check_capacity(enclosure_id)
    x("UPDATE animal SET enclosure_id=? WHERE animal_id=?", (enclosure_id, animal_id))


def set_animal_status(animal_id, status):
    x("UPDATE animal SET current_status=? WHERE animal_id=?", (status, animal_id))


# ---- MedicalController --------------------------------------------------
def add_diagnosis(animal_id, vet_id, diagnosis, notes):
    x("INSERT INTO medical_record(animal_id,vet_id,date,diagnosis,notes) VALUES(?,?,?,?,?)",
      (animal_id, vet_id, today(), diagnosis, notes))
    set_animal_status(animal_id, "Under Treatment")


def create_plan(animal_id, vet_id, medication, schedule, start, end):
    x("""INSERT INTO treatment_plan(animal_id,vet_id,medication,schedule,start_date,end_date)
         VALUES(?,?,?,?,?,?)""", (animal_id, vet_id, medication, schedule, str(start), str(end)))


def complete_plan(plan_id):
    x("UPDATE treatment_plan SET status='Completed' WHERE plan_id=?", (plan_id,))


def history(animal_id):
    return {
        "medical": q("SELECT * FROM medical_record WHERE animal_id=? ORDER BY record_id DESC", (animal_id,)),
        "plans": q("SELECT * FROM treatment_plan WHERE animal_id=? ORDER BY plan_id DESC", (animal_id,)),
        "logs": q("SELECT * FROM health_log WHERE animal_id=? ORDER BY log_id DESC", (animal_id,)),
        "release": q("SELECT * FROM release_record WHERE animal_id=? ORDER BY release_id DESC", (animal_id,)),
    }


def add_health_log(animal_id, caretaker_id, weight, temperature, behaviour, feeding, remarks):
    x("""INSERT INTO health_log(animal_id,caretaker_id,date,weight,temperature,behaviour,feeding,remarks)
         VALUES(?,?,?,?,?,?,?,?)""",
      (animal_id, caretaker_id, now(), weight, temperature, behaviour, feeding, remarks))


# ---- Release ------------------------------------------------------------
def assess_release(animal_id, vet_id, ready, notes):
    active = q("SELECT 1 FROM treatment_plan WHERE animal_id=? AND status='Active'", (animal_id,))
    if ready and active:
        raise RuleError("Cannot mark ready: animal still has an active treatment plan.")
    x("""INSERT INTO release_record(animal_id,vet_id,assessment_date,ready,notes)
         VALUES(?,?,?,?,?)""", (animal_id, vet_id, today(), int(ready), notes))
    if ready:
        set_animal_status(animal_id, "Ready for Release")


def pending_releases():
    return q("""SELECT r.release_id, r.animal_id, a.species, r.permit_no, r.assessment_date
                FROM release_record r JOIN animal a USING(animal_id)
                WHERE r.ready=1 AND r.outcome IS NULL""")


def record_permit(release_id, permit_no):
    x("UPDATE release_record SET permit_no=? WHERE release_id=?", (permit_no.strip(), release_id))


def complete_release(release_id, outcome, location):
    r = q("SELECT * FROM release_record WHERE release_id=?", (release_id,))[0]
    if not r["ready"]:
        raise RuleError("Animal has not been assessed as ready.")
    if outcome == "Released" and not (r["permit_no"] or "").strip():
        raise RuleError("A Forest Department permit number is required before release.")
    x("UPDATE release_record SET outcome=?, location=?, release_date=? WHERE release_id=?",
      (outcome, location, today(), release_id))
    set_animal_status(r["animal_id"], "Released" if outcome == "Released" else "Sanctuary/Zoo")


# ---- Volunteers ---------------------------------------------------------
def assign_task(volunteer_id, description, shift):
    x("INSERT INTO volunteer_task(volunteer_id,description,shift) VALUES(?,?,?)",
      (volunteer_id, description, shift))


def tasks(volunteer_id=None):
    sql = """SELECT t.*, u.name AS volunteer FROM volunteer_task t
             JOIN users u ON u.user_id=t.volunteer_id"""
    if volunteer_id:
        return q(sql + " WHERE t.volunteer_id=? ORDER BY task_id DESC", (volunteer_id,))
    return q(sql + " ORDER BY task_id DESC")


def update_task(task_id, status):
    x("UPDATE volunteer_task SET status=? WHERE task_id=?", (status, task_id))


# ---- Inventory ----------------------------------------------------------
def adjust_stock(item_id, delta):
    item = q("SELECT quantity FROM supply_item WHERE item_id=?", (item_id,))[0]
    if item["quantity"] + delta < 0:
        raise RuleError("Not enough stock.")
    x("UPDATE supply_item SET quantity=quantity+? WHERE item_id=?", (delta, item_id))


# ---- Donations & reports ------------------------------------------------
def donate(donor_id, amount, type_, purpose):
    if amount <= 0:
        raise RuleError("Amount must be positive.")
    x("INSERT INTO donation(donor_id,date,amount,type,purpose) VALUES(?,?,?,?,?)",
      (donor_id, today(), amount, type_, purpose))


def report():
    return {
        "cases": q("SELECT status, COUNT(*) AS n FROM rescue_case GROUP BY status"),
        "animals": q("SELECT current_status AS status, COUNT(*) AS n FROM animal GROUP BY current_status"),
        "donations": q("SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS n FROM donation")[0],
        "low_stock": q("SELECT name, quantity, unit FROM supply_item WHERE quantity<=min_level"),
    }
