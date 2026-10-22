"""Domain logic (control classes + entity behaviour from the class diagram)."""
import secrets
from datetime import date, datetime

from db import q, x

CASE_FLOW = ["Reported", "Assigned", "Captured", "At Centre", "Closed"]
ANIMAL_STATUSES = ["Admitted", "Under Treatment", "Ready for Release", "Released", "Sanctuary/Zoo"]
GONE = ("Released", "Sanctuary/Zoo")
ROLES = ["Coordinator", "Field Agent", "Veterinarian", "Caretaker", "Volunteer", "Donor"]
STAFF_ROLES = ["Coordinator", "Field Agent", "Veterinarian", "Caretaker", "Volunteer"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]


class RuleError(Exception):
    """Raised when a business rule is violated; shown to the user."""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def today() -> str:
    return date.today().isoformat()


# ---- Users / notifications / audit -------------------------------------
def get_user(user_id):
    r = q("SELECT * FROM users WHERE user_id=?", (user_id,))
    return r[0] if r else None


def users_by_role(role):
    return q("SELECT user_id,name,email,skills,phone FROM users WHERE role=? AND is_active=1", (role,))


def all_users():
    return q("""SELECT user_id,name,email,role,is_active,phone,skills,last_login,created_at
                FROM users ORDER BY role,name""")


def set_user_active(user_id, active):
    x("UPDATE users SET is_active=?, failed_attempts=0, locked_until=NULL WHERE user_id=?",
      (int(active), user_id))


def update_profile(user_id, name, phone, skills):
    if not name.strip():
        raise RuleError("Name is required.")
    x("UPDATE users SET name=?, phone=?, skills=? WHERE user_id=?", (name.strip(), phone, skills, user_id))


def notify(user_id, message):
    x("INSERT INTO notification(user_id,message,created_at) VALUES(?,?,?)", (user_id, message, now()))


def notify_role(role, message):
    for u in q("SELECT user_id FROM users WHERE role=? AND is_active=1", (role,)):
        notify(u["user_id"], message)


def notifications(user_id, unread_only=False):
    sql = "SELECT * FROM notification WHERE user_id=?" + (" AND is_read=0" if unread_only else "")
    return q(sql + " ORDER BY notif_id DESC LIMIT 100", (user_id,))


def unread_count(user_id):
    return q("SELECT COUNT(*) AS n FROM notification WHERE user_id=? AND is_read=0", (user_id,))[0]["n"]


def mark_all_read(user_id):
    x("UPDATE notification SET is_read=1 WHERE user_id=?", (user_id,))


def audit_log(limit=1000):
    return q("""SELECT a.ts, COALESCE(u.name,'System') AS user, COALESCE(u.role,'-') AS role,
                       a.action, a.detail
                FROM audit_log a LEFT JOIN users u USING(user_id) ORDER BY log_id DESC LIMIT ?""", (limit,))


# ---- Incident reporting & rescue ---------------------------------------
def report_incident(location, description, species="", priority="Medium", lat=None, lon=None, photo=None):
    """Citizen use case: no personal data is stored, only the report and a tracking code."""
    code = secrets.token_hex(4).upper()
    rid = x("""INSERT INTO incident_report(tracking_code,date_time,location,lat,lon,species,description,priority,photo)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (code, now(), location, lat, lon, species, description, priority, photo))
    cid = x("INSERT INTO rescue_case(report_id) VALUES(?)", (rid,))
    notify_role("Coordinator", f"New {priority.lower()}-priority report #{cid}: {location}")
    return cid, code


def track_report(code):
    """Public-safe view of a report's progress."""
    r = q("""SELECT r.tracking_code, r.date_time, r.location, r.species, r.priority, c.status,
                    c.case_id, a.current_status AS animal_status
             FROM incident_report r JOIN rescue_case c USING(report_id)
             LEFT JOIN animal a ON a.case_id=c.case_id
             WHERE r.tracking_code=?""", (code.strip().upper(),))
    return r[0] if r else None


def cases(agent_id=None):
    sql = """SELECT c.case_id, c.status, r.priority, r.location, r.species, r.description, r.date_time,
                    r.lat, r.lon, r.photo, r.tracking_code, u.name AS agent, c.agent_id, c.notes
             FROM rescue_case c JOIN incident_report r USING(report_id)
             LEFT JOIN users u ON u.user_id=c.agent_id"""
    args = ()
    if agent_id:
        sql += " WHERE c.agent_id=?"
        args = (agent_id,)
    return q(sql + """ ORDER BY (c.status='Closed'),
                       CASE r.priority WHEN 'Critical' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END,
                       c.case_id DESC""", args)


def assign_agent(case_id, agent_id):
    case = q("SELECT status FROM rescue_case WHERE case_id=?", (case_id,))[0]
    if case["status"] not in ("Reported", "Assigned"):
        raise RuleError("Only Reported/Assigned cases can be (re)assigned.")
    x("UPDATE rescue_case SET agent_id=?, status='Assigned', assigned_date=? WHERE case_id=?",
      (agent_id, today(), case_id))
    notify(agent_id, f"You were assigned to rescue case #{case_id}")


def advance_case(case_id, notes=""):
    case = q("SELECT status FROM rescue_case WHERE case_id=?", (case_id,))[0]
    i = CASE_FLOW.index(case["status"])
    if case["status"] == "Reported":
        raise RuleError("Assign a field agent first.")
    if case["status"] in ("At Centre", "Closed"):
        raise RuleError("Register the animal at intake to close this case.")
    nxt = CASE_FLOW[i + 1]
    x("UPDATE rescue_case SET status=?, notes=notes||? WHERE case_id=?",
      (nxt, f"\n[{now()}] {nxt}: {notes}" if notes else f"\n[{now()}] {nxt}", case_id))
    if nxt == "At Centre":
        notify_role("Veterinarian", f"Rescue case #{case_id} has arrived at the centre - intake needed")
    return nxt


# ---- Enclosures & animals ----------------------------------------------
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


def register_animal(species, age, gender, enclosure_id, case_id=None, tag_id=""):
    _check_capacity(enclosure_id)
    aid = x("""INSERT INTO animal(case_id,species,age,gender,tag_id,enclosure_id,intake_date)
               VALUES(?,?,?,?,?,?,?)""", (case_id, species, age, gender, tag_id, enclosure_id, today()))
    if case_id:
        x("UPDATE rescue_case SET status='Closed' WHERE case_id=?", (case_id,))
        x("""UPDATE incident_report SET status='Closed'
             WHERE report_id=(SELECT report_id FROM rescue_case WHERE case_id=?)""", (case_id,))
    return aid


def animals(include_gone=True, search="", statuses=None):
    rows = q("""SELECT a.*, e.type AS enclosure FROM animal a
                LEFT JOIN enclosure e USING(enclosure_id) ORDER BY a.animal_id DESC""")
    if not include_gone:
        rows = [r for r in rows if r["current_status"] not in GONE]
    if statuses:
        rows = [r for r in rows if r["current_status"] in statuses]
    if search.strip():
        s = search.strip().lower()
        rows = [r for r in rows if s in f"{r['species']} {r['tag_id']} {r['animal_id']}".lower()]
    return rows


def assign_enclosure(animal_id, enclosure_id):
    _check_capacity(enclosure_id)
    x("UPDATE animal SET enclosure_id=? WHERE animal_id=?", (enclosure_id, animal_id))


def set_animal_status(animal_id, status):
    x("UPDATE animal SET current_status=? WHERE animal_id=?", (status, animal_id))


# ---- Medical ------------------------------------------------------------
def add_diagnosis(animal_id, vet_id, diagnosis, notes):
    x("INSERT INTO medical_record(animal_id,vet_id,date,diagnosis,notes) VALUES(?,?,?,?,?)",
      (animal_id, vet_id, today(), diagnosis, notes))
    set_animal_status(animal_id, "Under Treatment")


def create_plan(animal_id, vet_id, medication, schedule, start, end):
    if str(end) < str(start):
        raise RuleError("End date is before start date.")
    x("""INSERT INTO treatment_plan(animal_id,vet_id,medication,schedule,start_date,end_date)
         VALUES(?,?,?,?,?,?)""", (animal_id, vet_id, medication, schedule, str(start), str(end)))


def complete_plan(plan_id):
    x("UPDATE treatment_plan SET status='Completed' WHERE plan_id=?", (plan_id,))


def schedule_surgery(animal_id, vet_id, when, procedure):
    x("INSERT INTO surgery(animal_id,vet_id,scheduled_at,procedure) VALUES(?,?,?,?)",
      (animal_id, vet_id, str(when), procedure))


def update_surgery(surgery_id, status, notes=""):
    x("UPDATE surgery SET status=?, notes=? WHERE surgery_id=?", (status, notes, surgery_id))


def upcoming_surgeries():
    return q("""SELECT s.surgery_id, s.animal_id, a.species, s.scheduled_at, s.procedure, s.status
                FROM surgery s JOIN animal a USING(animal_id)
                WHERE s.status='Scheduled' ORDER BY s.scheduled_at""")


def history(animal_id):
    return {
        "medical": q("SELECT date,diagnosis,notes FROM medical_record WHERE animal_id=? ORDER BY record_id DESC", (animal_id,)),
        "plans": q("SELECT plan_id,medication,schedule,start_date,end_date,status FROM treatment_plan WHERE animal_id=? ORDER BY plan_id DESC", (animal_id,)),
        "surgeries": q("SELECT surgery_id,scheduled_at,procedure,status,notes FROM surgery WHERE animal_id=? ORDER BY surgery_id DESC", (animal_id,)),
        "logs": q("SELECT date,weight,temperature,behaviour,feeding,remarks FROM health_log WHERE animal_id=? ORDER BY log_id", (animal_id,)),
        "feeding": q("SELECT * FROM feeding WHERE animal_id=?", (animal_id,)),
        "release": q("SELECT assessment_date,ready,permit_no,outcome,release_date,location,notes FROM release_record WHERE animal_id=? ORDER BY release_id DESC", (animal_id,)),
        "tracking": q("SELECT date,lat,lon,notes FROM tracking WHERE animal_id=? ORDER BY track_id", (animal_id,)),
    }


# ---- Daily care ---------------------------------------------------------
def add_health_log(animal_id, caretaker_id, weight, temperature, behaviour, feeding_, remarks):
    x("""INSERT INTO health_log(animal_id,caretaker_id,date,weight,temperature,behaviour,feeding,remarks)
         VALUES(?,?,?,?,?,?,?,?)""",
      (animal_id, caretaker_id, now(), weight, temperature, behaviour, feeding_, remarks))
    if behaviour in ("Lethargic", "Not eating") or temperature >= 40:
        notify_role("Veterinarian", f"Animal #{animal_id}: {behaviour}, {temperature:.1f}°C - please review")


def add_feeding(animal_id, meal_time, food, quantity):
    x("INSERT INTO feeding(animal_id,meal_time,food,quantity) VALUES(?,?,?,?)",
      (animal_id, meal_time, food, quantity))


def mark_fed(feed_id):
    x("UPDATE feeding SET last_fed=? WHERE feed_id=?", (today(), feed_id))


def feeding_today():
    return q("""SELECT f.feed_id, f.animal_id, a.species, f.meal_time, f.food, f.quantity,
                       (f.last_fed=?) AS fed
                FROM feeding f JOIN animal a USING(animal_id)
                WHERE a.current_status NOT IN ('Released','Sanctuary/Zoo')
                ORDER BY fed, f.meal_time""", (today(),))


# ---- Release ------------------------------------------------------------
def assess_release(animal_id, vet_id, ready, notes):
    if ready and q("SELECT 1 FROM treatment_plan WHERE animal_id=? AND status='Active'", (animal_id,)):
        raise RuleError("Cannot mark ready: animal still has an active treatment plan.")
    if ready and q("SELECT 1 FROM surgery WHERE animal_id=? AND status='Scheduled'", (animal_id,)):
        raise RuleError("Cannot mark ready: a surgery is still scheduled.")
    x("""INSERT INTO release_record(animal_id,vet_id,assessment_date,ready,notes)
         VALUES(?,?,?,?,?)""", (animal_id, vet_id, today(), int(ready), notes))
    if ready:
        set_animal_status(animal_id, "Ready for Release")
        notify_role("Coordinator", f"Animal #{animal_id} is ready for release - permit needed")


def pending_releases():
    return q("""SELECT r.release_id, r.animal_id, a.species, r.permit_no, r.assessment_date
                FROM release_record r JOIN animal a USING(animal_id)
                WHERE r.ready=1 AND r.outcome IS NULL""")


def record_permit(release_id, permit_no):
    x("UPDATE release_record SET permit_no=? WHERE release_id=?", (permit_no.strip(), release_id))


def complete_release(release_id, outcome, location, tag_id=""):
    r = q("SELECT * FROM release_record WHERE release_id=?", (release_id,))[0]
    if not r["ready"]:
        raise RuleError("Animal has not been assessed as ready.")
    if outcome == "Released" and not (r["permit_no"] or "").strip():
        raise RuleError("A Forest Department permit number is required before release.")
    x("UPDATE release_record SET outcome=?, location=?, release_date=? WHERE release_id=?",
      (outcome, location, today(), release_id))
    set_animal_status(r["animal_id"], "Released" if outcome == "Released" else "Sanctuary/Zoo")
    if tag_id.strip():
        x("UPDATE animal SET tag_id=? WHERE animal_id=?", (tag_id.strip(), r["animal_id"]))


def add_tracking(animal_id, lat, lon, notes):
    a = q("SELECT current_status FROM animal WHERE animal_id=?", (animal_id,))[0]
    if a["current_status"] != "Released":
        raise RuleError("Only released animals can be tracked.")
    x("INSERT INTO tracking(animal_id,date,lat,lon,notes) VALUES(?,?,?,?,?)",
      (animal_id, now(), lat, lon, notes))


def success_stories(limit=20):
    return q("""SELECT a.species, r.release_date, r.outcome, r.location FROM release_record r
                JOIN animal a USING(animal_id) WHERE r.outcome IS NOT NULL
                ORDER BY r.release_id DESC LIMIT ?""", (limit,))


# ---- Volunteers: tasks, attendance, training ---------------------------
def assign_task(volunteer_id, description, shift):
    x("INSERT INTO volunteer_task(volunteer_id,description,shift) VALUES(?,?,?)",
      (volunteer_id, description, shift))
    notify(volunteer_id, f"New task ({shift}): {description}")


def tasks(volunteer_id=None):
    sql = """SELECT t.task_id,t.volunteer_id,u.name AS volunteer,t.description,t.shift,t.status
             FROM volunteer_task t JOIN users u ON u.user_id=t.volunteer_id"""
    if volunteer_id:
        return q(sql + " WHERE t.volunteer_id=? ORDER BY task_id DESC", (volunteer_id,))
    return q(sql + " ORDER BY task_id DESC")


def update_task(task_id, status):
    x("UPDATE volunteer_task SET status=? WHERE task_id=?", (status, task_id))


def open_attendance(user_id):
    r = q("SELECT * FROM attendance WHERE user_id=? AND check_out IS NULL", (user_id,))
    return r[0] if r else None


def check_in(user_id):
    if open_attendance(user_id):
        raise RuleError("You are already checked in.")
    x("INSERT INTO attendance(user_id,check_in) VALUES(?,?)", (user_id, now()))


def check_out(user_id):
    a = open_attendance(user_id)
    if not a:
        raise RuleError("You are not checked in.")
    x("UPDATE attendance SET check_out=? WHERE att_id=?", (now(), a["att_id"]))


def attendance(user_id=None):
    sql = """SELECT u.name, a.check_in, a.check_out FROM attendance a JOIN users u USING(user_id)"""
    if user_id:
        return q(sql + " WHERE a.user_id=? ORDER BY att_id DESC", (user_id,))
    return q(sql + " ORDER BY att_id DESC LIMIT 200")


def add_training(user_id, title, completed_on, expires_on):
    x("INSERT INTO training(user_id,title,completed_on,expires_on) VALUES(?,?,?,?)",
      (user_id, title, str(completed_on), str(expires_on) if expires_on else ""))


def trainings(user_id=None):
    sql = """SELECT u.name, t.title, t.completed_on, t.expires_on FROM training t JOIN users u USING(user_id)"""
    if user_id:
        return q(sql + " WHERE t.user_id=? ORDER BY training_id DESC", (user_id,))
    return q(sql + " ORDER BY training_id DESC")


# ---- Inventory ----------------------------------------------------------
def adjust_stock(item_id, delta):
    item = q("SELECT quantity FROM supply_item WHERE item_id=?", (item_id,))[0]
    if item["quantity"] + delta < 0:
        raise RuleError("Not enough stock.")
    x("UPDATE supply_item SET quantity=quantity+? WHERE item_id=?", (delta, item_id))


def add_item(name, type_, qty, unit, expiry, min_level):
    x("INSERT INTO supply_item(name,type,quantity,unit,expiry_date,min_level) VALUES(?,?,?,?,?,?)",
      (name, type_, qty, unit, expiry, min_level))


def set_equipment_status(equipment_id, status):
    x("""UPDATE equipment SET status=?,
         last_maintenance=CASE WHEN ?='Under maintenance' THEN ? ELSE last_maintenance END
         WHERE equipment_id=?""", (status, status, today(), equipment_id))


# ---- Donations ----------------------------------------------------------
def donate(donor_id, amount, type_, purpose):
    if amount <= 0:
        raise RuleError("Amount must be positive.")
    receipt = "RCP-" + secrets.token_hex(3).upper()
    x("INSERT INTO donation(receipt_no,donor_id,date,amount,type,purpose) VALUES(?,?,?,?,?,?)",
      (receipt, donor_id, today(), amount, type_, purpose))
    notify_role("Coordinator", f"New {type_.lower()} donation: {amount:.0f} ({purpose or 'general'})")
    return receipt


def donations(donor_id=None):
    sql = """SELECT d.receipt_no,d.date,u.name AS donor,d.amount,d.type,d.purpose,d.status
             FROM donation d JOIN users u ON u.user_id=d.donor_id"""
    if donor_id:
        return q(sql + " WHERE d.donor_id=? ORDER BY donation_id DESC", (donor_id,))
    return q(sql + " ORDER BY donation_id DESC")


# ---- Reports ------------------------------------------------------------
def public_stats():
    return {
        "rescued": q("SELECT COUNT(*) AS n FROM animal")[0]["n"],
        "in_care": q("SELECT COUNT(*) AS n FROM animal WHERE current_status NOT IN ('Released','Sanctuary/Zoo')")[0]["n"],
        "released": q("SELECT COUNT(*) AS n FROM animal WHERE current_status='Released'")[0]["n"],
        "volunteers": q("SELECT COUNT(*) AS n FROM users WHERE role='Volunteer' AND is_active=1")[0]["n"],
    }


def report():
    return {
        "cases": q("SELECT status, COUNT(*) AS n FROM rescue_case GROUP BY status"),
        "animals": q("SELECT current_status AS status, COUNT(*) AS n FROM animal GROUP BY current_status"),
        "species": q("SELECT species, COUNT(*) AS n FROM animal GROUP BY species ORDER BY n DESC"),
        "donations_by_month": q("""SELECT substr(date,1,7) AS month, SUM(amount) AS total
                                   FROM donation GROUP BY month ORDER BY month"""),
        "donations": q("SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS n FROM donation")[0],
        "low_stock": q("SELECT name, quantity, unit FROM supply_item WHERE quantity<=min_level"),
        "open_cases": q("SELECT COUNT(*) AS n FROM rescue_case WHERE status!='Closed'")[0]["n"],
    }
