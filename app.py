"""Wildlife Rescue & Rehabilitation Management System - Streamlit frontend.

Run:  streamlit run app.py
"""
import pandas as pd
import streamlit as st

import models as m
from db import init_db, q

st.set_page_config(page_title="Wildlife Rescue", page_icon="🦉", layout="wide")
init_db()


def guard(fn, *args, ok="Saved."):
    """Run a model call, showing business-rule errors instead of crashing."""
    try:
        fn(*args)
        st.success(ok)
        return True
    except m.RuleError as e:
        st.error(str(e))
        return False


def table(rows, empty="Nothing here yet."):
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.info(empty)


def pick(label, rows, fmt, key=None):
    if not rows:
        st.info(f"No options for “{label}”.")
        return None
    return st.selectbox(label, rows, format_func=fmt, key=key)


def animal_fmt(a):
    return f"#{a['animal_id']} {a['species']} ({a['current_status']})"


def active_animals():
    return m.animals(status_not_in=("Released", "Sanctuary/Zoo"))


# ---- Pages --------------------------------------------------------------
def page_report():
    st.header("Report an injured or distressed animal")
    st.caption("No personal details are stored - only the report itself.")
    with st.form("report", clear_on_submit=True):
        loc = st.text_input("Location (address / landmark / GPS)")
        desc = st.text_area("What did you see? (species, injury, behaviour)")
        if st.form_submit_button("Submit report", type="primary"):
            if loc.strip() and desc.strip():
                rid, cid = m.report_incident(loc.strip(), desc.strip())
                st.success(f"Thank you! Report #{rid} logged as rescue case #{cid}. A coordinator will dispatch help.")
            else:
                st.error("Location and description are required.")


def page_dashboard():
    st.header("Operational dashboard")
    r = m.report()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rescue cases", sum(x["n"] for x in r["cases"]))
    c2.metric("Animals tracked", sum(x["n"] for x in r["animals"]))
    c3.metric("Donations (₹/units)", f"{r['donations']['total']:.0f}")
    c4.metric("Low-stock items", len(r["low_stock"]))
    a, b = st.columns(2)
    with a:
        st.subheader("Cases by status")
        table(r["cases"])
    with b:
        st.subheader("Animals by status")
        table(r["animals"])
    st.subheader("Enclosure usage")
    table([{"Enclosure": e["enclosure_id"], "Type": e["type"], "Quarantine": bool(e["quarantine"]),
            "Occupancy": f"{e['occupancy']}/{e['capacity']}"} for e in m.enclosures()])
    if r["low_stock"]:
        st.warning("Low stock: " + ", ".join(f"{i['name']} ({i['quantity']} {i['unit']})" for i in r["low_stock"]))


def page_cases(user):
    st.header("Rescue cases")
    is_coord = user["role"] == "Coordinator"
    cases = m.open_cases()
    if not is_coord:
        cases = [c for c in cases if c["agent_id"] == user["user_id"]]
    table([{k: c[k] for k in ("case_id", "status", "location", "description", "date_time", "agent")}
           for c in cases], "No cases.")
    open_ = [c for c in cases if c["status"] != "Closed"]
    if is_coord:
        st.subheader("Assign field agent")
        agents = m.users_by_role("Field Agent")
        assignable = [c for c in open_ if c["status"] in ("Reported", "Assigned")]
        c = pick("Case", assignable, lambda c: f"#{c['case_id']} {c['location']} [{c['status']}]", "assign_case")
        ag = pick("Field agent", agents, lambda a: a["name"], "assign_agent")
        if c and ag and st.button("Assign"):
            if guard(m.assign_agent, c["case_id"], ag["user_id"], ok="Agent assigned."):
                st.rerun()
    else:
        st.subheader("Update progress")
        c = pick("Case", [x for x in open_ if x["status"] != "Closed"],
                 lambda c: f"#{c['case_id']} {c['location']} [{c['status']}]", "adv_case")
        note = st.text_input("Note (e.g. captured near river, transporting)")
        if c and st.button("Advance to next status"):
            try:
                nxt = m.advance_case(c["case_id"], note)
                st.success(f"Case moved to {nxt}.")
                st.rerun()
            except m.RuleError as e:
                st.error(str(e))


def page_intake():
    st.header("Animal intake")
    cases = [c for c in m.open_cases() if c["status"] == "At Centre"]
    c = pick("From rescue case (optional)", [None] + cases,
             lambda c: "Walk-in / no case" if c is None else f"#{c['case_id']} {c['location']}", "intake_case")
    encl = m.enclosures()
    with st.form("intake", clear_on_submit=True):
        species = st.text_input("Species")
        age = st.number_input("Age (years)", 0, 100, 1)
        gender = st.selectbox("Gender", ["Unknown", "Male", "Female"])
        e = st.selectbox("Enclosure", encl, format_func=lambda e: (
            f"#{e['enclosure_id']} {e['type']} {e['occupancy']}/{e['capacity']}"
            + (" [Quarantine]" if e["quarantine"] else "")))
        if st.form_submit_button("Register animal", type="primary"):
            if not species.strip():
                st.error("Species is required.")
            else:
                try:
                    aid = m.register_animal(species.strip(), age, gender, e["enclosure_id"],
                                            c["case_id"] if c else None)
                    st.success(f"Animal #{aid} admitted.")
                except m.RuleError as err:
                    st.error(str(err))
    st.subheader("Move an animal to another enclosure")
    a = pick("Animal", active_animals(), animal_fmt, "mv_animal")
    e2 = pick("New enclosure", encl, lambda e: f"#{e['enclosure_id']} {e['type']} {e['occupancy']}/{e['capacity']}", "mv_enc")
    if a and e2 and st.button("Move"):
        guard(m.assign_enclosure, a["animal_id"], e2["enclosure_id"], ok="Animal moved.")


def page_medical(user):
    st.header("Medical care")
    a = pick("Animal", active_animals(), animal_fmt, "med_animal")
    if not a:
        return
    t1, t2, t3 = st.tabs(["Diagnose", "Treatment plan", "History"])
    with t1:
        with st.form("diag", clear_on_submit=True):
            dx = st.text_input("Diagnosis")
            notes = st.text_area("Exam notes")
            if st.form_submit_button("Save medical record") and dx.strip():
                m.add_diagnosis(a["animal_id"], user["user_id"], dx.strip(), notes)
                st.success("Record saved; animal marked Under Treatment.")
    with t2:
        with st.form("plan", clear_on_submit=True):
            med = st.text_input("Medication / treatment")
            sched = st.text_input("Schedule (e.g. twice daily)")
            c1, c2 = st.columns(2)
            start, end = c1.date_input("Start"), c2.date_input("End")
            if st.form_submit_button("Create plan") and med.strip():
                m.create_plan(a["animal_id"], user["user_id"], med.strip(), sched, start, end)
                st.success("Treatment plan created.")
        active = [p for p in m.history(a["animal_id"])["plans"] if p["status"] == "Active"]
        p = pick("Mark plan completed", active, lambda p: f"#{p['plan_id']} {p['medication']}", "done_plan")
        if p and st.button("Mark completed"):
            m.complete_plan(p["plan_id"])
            st.rerun()
    with t3:
        h = m.history(a["animal_id"])
        for title, key in [("Medical records", "medical"), ("Treatment plans", "plans"),
                           ("Health logs", "logs"), ("Release records", "release")]:
            st.subheader(title)
            table(h[key])


def page_care(user):
    st.header("Daily care")
    a = pick("Animal", active_animals(), animal_fmt, "care_animal")
    if not a:
        return
    with st.form("log", clear_on_submit=True):
        c1, c2 = st.columns(2)
        w = c1.number_input("Weight (kg)", 0.0, 2000.0, 0.0, 0.1)
        t = c2.number_input("Temperature (°C)", 0.0, 50.0, 37.0, 0.1)
        beh = st.selectbox("Behaviour", ["Calm", "Active", "Lethargic", "Aggressive", "Stressed", "Not eating"])
        feed = st.text_input("Feeding given")
        rem = st.text_area("Remarks")
        if st.form_submit_button("Add health log", type="primary"):
            m.add_health_log(a["animal_id"], user["user_id"], w, t, beh, feed, rem)
            st.success("Logged.")
    h = m.history(a["animal_id"])
    st.subheader("Active treatment plans")
    table([p for p in h["plans"] if p["status"] == "Active"], "No active plans.")
    st.subheader("Recent logs")
    table(h["logs"])
    st.subheader("Enclosures")
    table([{"id": e["enclosure_id"], "type": e["type"], "quarantine": bool(e["quarantine"]),
            "occupancy": f"{e['occupancy']}/{e['capacity']}"} for e in m.enclosures()])


def page_release(user):
    st.header("Release & transfer")
    role = user["role"]
    if role == "Veterinarian":
        st.subheader("Release-readiness assessment")
        a = pick("Animal", [x for x in active_animals() if x["current_status"] != "Ready for Release"],
                 animal_fmt, "rel_animal")
        ready = st.checkbox("Animal is fit for release / transfer")
        notes = st.text_area("Assessment notes")
        if a and st.button("Save assessment"):
            guard(m.assess_release, a["animal_id"], user["user_id"], ready, notes, ok="Assessment saved.")
    if role == "Coordinator":
        st.subheader("Pending releases")
        pend = m.pending_releases()
        table(pend, "No animals awaiting release.")
        r = pick("Release record", pend, lambda r: f"#{r['release_id']} animal #{r['animal_id']} {r['species']}", "rel_rec")
        if r:
            permit = st.text_input("Forest Department permit no.", value=r["permit_no"] or "")
            if st.button("Save permit"):
                m.record_permit(r["release_id"], permit)
                st.success("Permit recorded.")
            outcome = st.radio("Outcome", ["Released", "Sanctuary/Zoo"], horizontal=True)
            loc = st.text_input("Release / transfer location (add GPS or tag ID if tracked)")
            if st.button("Complete", type="primary"):
                if guard(m.complete_release, r["release_id"], outcome, loc, ok="Done."):
                    st.rerun()
    st.subheader("Completed")
    table(q("""SELECT r.release_id, r.animal_id, a.species, r.permit_no, r.outcome, r.location, r.release_date
               FROM release_record r JOIN animal a USING(animal_id) WHERE r.outcome IS NOT NULL"""))


def page_staff():
    st.header("Staff & volunteers")
    t1, t2 = st.tabs(["Register", "Assign tasks"])
    with t1:
        with st.form("reg", clear_on_submit=True):
            name = st.text_input("Name")
            email = st.text_input("Email")
            pw = st.text_input("Temporary password", type="password")
            role = st.selectbox("Role", m.ROLES)
            skills = st.text_input("Skills / certifications")
            if st.form_submit_button("Register"):
                if name and email and pw:
                    guard(m.register_user, name, email, pw, role, skills, ok="User registered.")
                else:
                    st.error("Name, email and password are required.")
        table(q("SELECT user_id,name,email,role,skills FROM users"))
    with t2:
        v = pick("Volunteer", m.users_by_role("Volunteer"), lambda u: u["name"], "task_vol")
        desc = st.text_input("Task")
        shift = st.selectbox("Shift", ["Morning", "Afternoon", "Evening", "Night"])
        if v and desc and st.button("Assign task"):
            m.assign_task(v["user_id"], desc, shift)
            st.success("Assigned.")
        table(m.tasks())


def page_my_tasks(user):
    st.header("My tasks")
    rows = m.tasks(user["user_id"])
    table(rows, "No tasks assigned.")
    t = pick("Task", [r for r in rows if r["status"] != "Done"], lambda t: f"#{t['task_id']} {t['description']}", "my_task")
    status = st.radio("Status", ["In progress", "Done"], horizontal=True)
    if t and st.button("Update"):
        m.update_task(t["task_id"], status)
        st.rerun()


def page_inventory():
    st.header("Inventory & assets")
    t1, t2 = st.tabs(["Supplies", "Equipment / vehicles"])
    with t1:
        items = q("SELECT * FROM supply_item")
        table([{**i, "LOW": i["quantity"] <= i["min_level"]} for i in items])
        i = pick("Item", items, lambda i: f"{i['name']} ({i['quantity']} {i['unit']})", "stock_item")
        delta = st.number_input("Change quantity (+ add / − use)", value=0, step=1)
        if i and st.button("Apply"):
            if guard(m.adjust_stock, i["item_id"], int(delta), ok="Stock updated."):
                st.rerun()
        with st.expander("Add new supply item"):
            with st.form("newitem", clear_on_submit=True):
                n = st.text_input("Name")
                ty = st.selectbox("Type", ["Medical", "Food"])
                qty = st.number_input("Quantity", 0, 100000, 0)
                unit = st.text_input("Unit", "units")
                mn = st.number_input("Low-stock level", 0, 1000, 5)
                if st.form_submit_button("Add") and n:
                    from db import x
                    x("INSERT INTO supply_item(name,type,quantity,unit,min_level) VALUES(?,?,?,?,?)",
                      (n, ty, qty, unit, mn))
                    st.rerun()
    with t2:
        eq = q("SELECT * FROM equipment")
        table(eq)
        e = pick("Equipment", eq, lambda e: e["name"], "eq_pick")
        s = st.selectbox("Status", ["Available", "In use", "Under maintenance"])
        if e and st.button("Update status"):
            from db import x
            x("UPDATE equipment SET status=?, last_maintenance=CASE WHEN ?='Under maintenance' THEN ? ELSE last_maintenance END "
              "WHERE equipment_id=?", (s, s, m.today(), e["equipment_id"]))
            st.rerun()


def page_donate(user):
    st.header("Donate")
    with st.form("don", clear_on_submit=True):
        amt = st.number_input("Amount / value", 0.0, step=100.0)
        ty = st.selectbox("Type", ["Money", "Supplies"])
        purpose = st.text_input("Purpose (e.g. medicine, food, enclosure repair)")
        if st.form_submit_button("Donate", type="primary"):
            guard(m.donate, user["user_id"], amt, ty, purpose, ok="Thank you for your support!")
    st.subheader("My donation history")
    table(q("SELECT date,amount,type,purpose,status FROM donation WHERE donor_id=? ORDER BY donation_id DESC",
            (user["user_id"],)))


def page_donations():
    st.header("Donations")
    rows = q("""SELECT d.donation_id,d.date,u.name AS donor,d.amount,d.type,d.purpose,d.status
                FROM donation d JOIN users u ON u.user_id=d.donor_id ORDER BY donation_id DESC""")
    table(rows, "No donations yet.")
    if rows:
        st.metric("Total", f"{sum(r['amount'] for r in rows):.0f}")


# ---- Auth & routing -----------------------------------------------------
def login_page():
    st.title("🦉 Wildlife Rescue & Rehabilitation")
    t1, t2 = st.tabs(["Report an animal (public)", "Staff / donor login"])
    with t1:
        page_report()
    with t2:
        with st.form("login"):
            email = st.text_input("Email")
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", type="primary"):
                u = m.login(email, pw)
                if u:
                    st.session_state.user = u
                    st.rerun()
                st.error("Invalid credentials.")
        with st.expander("Demo accounts"):
            st.code("coordinator@wild.org / coord123\nagent@wild.org / agent123\n"
                    "vet@wild.org / vet123\ncaretaker@wild.org / care123\n"
                    "volunteer@wild.org / vol123\ndonor@wild.org / donor123")


def pages_for(user):
    uid = user
    return {
        "Coordinator": {
            "Dashboard": page_dashboard, "Rescue cases": lambda: page_cases(uid),
            "Release permits": lambda: page_release(uid), "Staff & volunteers": page_staff,
            "Inventory": page_inventory, "Donations": page_donations,
            "Animals (view)": lambda: page_medical_view(),
        },
        "Field Agent": {"My cases": lambda: page_cases(uid)},
        "Veterinarian": {"Intake": page_intake, "Medical care": lambda: page_medical(uid),
                         "Release assessment": lambda: page_release(uid)},
        "Caretaker": {"Intake": page_intake, "Daily care": lambda: page_care(uid), "Inventory": page_inventory},
        "Volunteer": {"My tasks": lambda: page_my_tasks(uid)},
        "Donor": {"Donate": lambda: page_donate(uid)},
    }[user["role"]]


def page_medical_view():
    st.header("All animals")
    table(m.animals())


def main():
    user = st.session_state.get("user")
    if not user:
        login_page()
        return
    pages = pages_for(user)
    with st.sidebar:
        st.markdown(f"**{user['name']}**  \n{user['role']}")
        choice = st.radio("Menu", list(pages), label_visibility="collapsed")
        if st.button("Log out"):
            del st.session_state["user"]
            st.rerun()
    pages[choice]()


main()
