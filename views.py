"""All Streamlit pages. app.py wires them into navigation by role."""
import secrets
from pathlib import Path

import pandas as pd
import streamlit as st

import auth
import models as m
from db import UPLOAD_DIR, q

PAGE: dict = {}  # filled by app.py so pages can link to each other


# ---- helpers ------------------------------------------------------------
def me() -> dict:
    return st.session_state["user"]


def table(rows, empty="Nothing here yet.", **kw):
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, **kw)
    else:
        st.info(empty)


def guard(fn, *args, ok="Saved.", **kw) -> bool:
    try:
        fn(*args, **kw)
        st.toast(ok, icon=":material/check_circle:")
        return True
    except (m.RuleError, ValueError) as e:
        st.error(str(e))
        return False


def pick(label, rows, fmt, key=None):
    if not rows:
        st.caption(f"No options available for “{label}”.")
        return None
    return st.selectbox(label, rows, format_func=fmt, key=key)


def animal_fmt(a):
    tag = f" · tag {a['tag_id']}" if a.get("tag_id") else ""
    return f"#{a['animal_id']} {a['species']}{tag} ({a['current_status']})"


def active_animals():
    return m.animals(include_gone=False)


def save_photo(upload) -> str | None:
    if upload is None:
        return None
    ext = Path(upload.name).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png"):
        raise ValueError("Photo must be a JPG or PNG.")
    if upload.size > 5 * 1024 * 1024:
        raise ValueError("Photo must be under 5 MB.")
    name = f"{secrets.token_hex(8)}{ext}"
    (UPLOAD_DIR / name).write_bytes(upload.getvalue())
    return name


def csv_button(label, rows, filename):
    if rows:
        st.download_button(label, pd.DataFrame(rows).to_csv(index=False), filename, "text/csv",
                           icon=":material/download:")


def bar(rows, index, value):
    if rows:
        st.bar_chart(pd.DataFrame(rows).set_index(index)[value])
    else:
        st.caption("No data yet.")


# ---- public pages -------------------------------------------------------
IMG = Path(__file__).parent / "site" / "img"


def home():
    s = m.public_stats()
    left, right = st.columns([3, 2], gap="large", vertical_alignment="center")
    with left:
        st.caption(":material/pets: WILDLIFE RESCUE & REHABILITATION")
        st.title("See an injured animal? Help is one form away.")
        st.markdown("Report distressed wildlife in a minute, with **no sign-up and no personal details**. "
                    "Follow the rescue, treatment and release with a tracking code.")
        c = st.columns(3)
        c[0].page_link(PAGE["report"], label="Report an animal", icon=":material/report:", width="stretch")
        c[1].page_link(PAGE["track"], label="Track a report", icon=":material/search:", width="stretch")
        c[2].page_link(PAGE["signup"], label="Volunteer or donate", icon=":material/favorite:", width="stretch")
    with right:
        if (IMG / "tiger.jpg").exists():
            st.image(str(IMG / "tiger.jpg"), alt="Bengal tiger resting in the forest", width="stretch")

    st.write("")
    c = st.columns(4)
    c[0].metric("Animals rescued", s["rescued"], border=True)
    c[1].metric("Currently in care", s["in_care"], border=True)
    c[2].metric("Released / re-homed", s["released"], border=True)
    c[3].metric("Active volunteers", s["volunteers"], border=True)

    st.divider()
    st.header("How it works")
    steps = [
        (":material/report:", "1. Report", "Tell us where the animal is and what you see. Add a photo or location."),
        (":material/local_shipping:", "2. Rescue", "A coordinator dispatches a field agent who brings the animal in."),
        (":material/medical_services:", "3. Treat", "Vets diagnose and treat; caretakers feed and monitor its recovery."),
        (":material/forest:", "4. Release", "With Forest Department permission, healthy animals return to the wild."),
    ]
    for col, (icon, title, text) in zip(st.columns(4), steps):
        with col.container(border=True, height="stretch"):
            st.markdown(f"#### {icon} {title}")
            st.write(text)

    photos = [("elephant", "Indian elephant"), ("peacock", "Indian peafowl"), ("owlet", "Spotted owlet"),
              ("leopard", "Indian leopard")]
    if all((IMG / f"{k}.jpg").exists() for k, _ in photos):
        st.divider()
        st.header("The animals we help")
        for col, (key, name) in zip(st.columns(4), photos):
            col.image(str(IMG / f"{key}.jpg"), caption=name, alt=name, width="stretch")
        st.caption("Photos: Wikimedia Commons - Y. S. Krishnappa (CC BY-SA 3.0), K. Mondal (CC BY 4.0), "
                   "M. Mottakin, T. Mukherjee, C. J. Sharp (CC BY-SA 4.0).")

    st.divider()
    with st.container(border=True):
        a, b = st.columns([3, 1], vertical_alignment="center")
        a.subheader("Want to help?")
        a.write("Create a free account to volunteer your time or support the centre with a donation.")
        b.page_link(PAGE["signup"], label="Create an account", icon=":material/person_add:", width="stretch")


def report_page():
    st.title(":material/report: Report an animal")
    st.caption("No personal details are stored. You'll get a tracking code to follow progress.")
    with st.form("report", clear_on_submit=True):
        loc = st.text_input("Location *", placeholder="Street, landmark or area")
        species = st.text_input("Animal (if you know)", placeholder="e.g. peacock, snake, monkey")
        desc = st.text_area("What did you see? *", placeholder="Injury, behaviour, how long it's been there")
        priority = st.segmented_control("Urgency", m.PRIORITIES, default="Medium")
        with st.expander("Exact map location (optional)"):
            c1, c2 = st.columns(2)
            lat = c1.number_input("Latitude", -90.0, 90.0, 0.0, format="%.5f")
            lon = c2.number_input("Longitude", -180.0, 180.0, 0.0, format="%.5f")
        photo = st.file_uploader("Photo (optional, JPG/PNG up to 5 MB)", type=["jpg", "jpeg", "png"])
        if st.form_submit_button("Submit report", type="primary"):
            if not loc.strip() or not desc.strip():
                st.error("Location and description are required.")
            else:
                try:
                    name = save_photo(photo)
                    cid, code = m.report_incident(loc.strip(), desc.strip(), species.strip(),
                                                  priority or "Medium",
                                                  lat or None, lon or None, name)
                    st.success(f"Report received - case #{cid}. Your tracking code:")
                    st.code(code, language=None)
                    st.caption("Keep this code to check progress on the Track page.")
                except ValueError as e:
                    st.error(str(e))


def track_page():
    st.title(":material/search: Track a report")
    code = st.text_input("Tracking code", max_chars=8, placeholder="e.g. A1B2C3D4")
    if code:
        r = m.track_report(code)
        if not r:
            st.error("No report found with that code.")
        else:
            flow = m.CASE_FLOW
            st.progress((flow.index(r["status"]) + 1) / len(flow), text=f"Status: {r['status']}")
            c = st.columns(3)
            c[0].metric("Case", f"#{r['case_id']}")
            c[1].metric("Priority", r["priority"])
            c[2].metric("Animal status", r["animal_status"] or "Not yet admitted")
            st.write(f"Reported {r['date_time']} at {r['location']}")


def stories_page():
    st.title(":material/forest: Success stories")
    rows = m.success_stories()
    if not rows:
        st.info("No releases yet - check back soon.")
    for r in rows:
        icon = ":material/forest:" if r["outcome"] == "Released" else ":material/home:"
        st.markdown(f"{icon} **{r['species']}** - {r['outcome']} on {r['release_date']}"
                    + (f" at {r['location']}" if r["location"] else ""))


def login_page():
    st.title(":material/login: Sign in")
    _, col, _ = st.columns([1, 2, 1])
    with col.container(border=True):
        with st.form("login"):
            email = st.text_input("Email")
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in", type="primary", width="stretch"):
                user, msg = auth.authenticate(email, pw)
                if user:
                    st.session_state["user"] = user
                    st.rerun()
                st.error(msg)
        st.page_link(PAGE["signup"], label="New here? Create an account", icon=":material/person_add:")
        with st.expander("Demo accounts"):
            st.code("coordinator@wild.org  Coord@123\nagent@wild.org        Agent@123\n"
                    "vet@wild.org          Vet@1234\ncaretaker@wild.org   Care@123\n"
                    "volunteer@wild.org    Volun@123\ndonor@wild.org        Donor@123", language=None)


def signup_page():
    st.title(":material/person_add: Create an account")
    st.caption("Donors and volunteers can sign up here. Staff accounts are created by a coordinator.")
    _, col, _ = st.columns([1, 2, 1])
    with col.container(border=True):
        with st.form("signup"):
            role = st.segmented_control("I want to", auth.SELF_SIGNUP_ROLES, default="Donor",
                                        format_func=lambda r: "Donate" if r == "Donor" else "Volunteer")
            name = st.text_input("Full name")
            email = st.text_input("Email")
            phone = st.text_input("Phone (optional)")
            pw = st.text_input("Password", type="password", help="At least 8 characters with letters and digits")
            pw2 = st.text_input("Confirm password", type="password")
            if st.form_submit_button("Create account", type="primary", width="stretch"):
                if pw != pw2:
                    st.error("Passwords do not match.")
                else:
                    try:
                        uid = auth.create_user(name, email, pw, role or "Donor", phone)
                        auth.audit(uid, "signup", role)
                        st.success("Account created - you can sign in now.")
                    except ValueError as e:
                        st.error(str(e))


# ---- account pages ------------------------------------------------------
def profile_page():
    u = m.get_user(me()["user_id"])
    st.title(":material/account_circle: My profile")
    st.caption(f"{u['role']} · {u['email']} · member since {u['created_at']}")
    with st.form("profile"):
        name = st.text_input("Name", u["name"])
        phone = st.text_input("Phone", u["phone"])
        skills = st.text_input("Skills / notes", u["skills"])
        if st.form_submit_button("Save profile") and guard(m.update_profile, u["user_id"], name, phone, skills):
            st.session_state["user"] = m.get_user(u["user_id"])
    password_form(u)


def password_form(u):
    st.subheader("Change password")
    if u["must_change_pw"]:
        st.warning("You must set a new password before continuing.")
    with st.form("pw", clear_on_submit=True):
        old = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        new2 = st.text_input("Confirm new password", type="password")
        if st.form_submit_button("Update password"):
            if new != new2:
                st.error("New passwords do not match.")
            elif guard(auth.change_password, u["user_id"], old, new, ok="Password updated."):
                st.session_state["user"] = m.get_user(u["user_id"])
                st.rerun()


def force_password_page():
    st.title(":material/lock_reset: Set a new password")
    password_form(m.get_user(me()["user_id"]))


def notifications_page():
    st.title(":material/notifications: Notifications")
    rows = m.notifications(me()["user_id"])
    if not rows:
        st.info("You're all caught up.")
    for n in rows:
        st.markdown(f"{'' if n['is_read'] else ':material/fiber_manual_record: '}"
                    f"**{n['created_at']}** - {n['message']}")
    if rows and st.button("Mark all as read"):
        m.mark_all_read(me()["user_id"])
        st.rerun()


# ---- coordinator --------------------------------------------------------
def dashboard_page():
    st.title(":material/dashboard: Dashboard")
    r = m.report()
    c = st.columns(4)
    c[0].metric("Open cases", r["open_cases"])
    c[1].metric("Animals in care", m.public_stats()["in_care"])
    c[2].metric("Donations", f"{r['donations']['total']:.0f}")
    c[3].metric("Low-stock items", len(r["low_stock"]))
    if r["low_stock"]:
        st.warning("Low stock: " + ", ".join(f"{i['name']} ({i['quantity']} {i['unit']})" for i in r["low_stock"]))
    a, b = st.columns(2)
    with a.container(border=True):
        st.subheader("Cases by status")
        bar(r["cases"], "status", "n")
    with b.container(border=True):
        st.subheader("Animals by status")
        bar(r["animals"], "status", "n")
    a, b = st.columns(2)
    with a.container(border=True):
        st.subheader("Species rescued")
        bar(r["species"], "species", "n")
    with b.container(border=True):
        st.subheader("Donations by month")
        bar(r["donations_by_month"], "month", "total")
    st.subheader("Enclosure usage")
    table([{"Enclosure": f"#{e['enclosure_id']} {e['type']}", "Quarantine": bool(e["quarantine"]),
            "Occupied": e["occupancy"], "Capacity": e["capacity"]} for e in m.enclosures()])
    st.subheader("Upcoming surgeries")
    table(m.upcoming_surgeries(), "None scheduled.")


def cases_page():
    user = me()
    is_coord = user["role"] == "Coordinator"
    st.title(":material/emergency: Rescue cases" if is_coord else ":material/emergency: My cases")
    cs = m.cases(None if is_coord else user["user_id"])
    live = [c for c in cs if c["status"] != "Closed"]
    mapped = [{"lat": c["lat"], "lon": c["lon"]} for c in live if c["lat"] and c["lon"]]
    if mapped:
        with st.expander("Map of open cases", expanded=is_coord):
            st.map(pd.DataFrame(mapped), latitude="lat", longitude="lon", size=40)
    cols = ["case_id", "priority", "status", "species", "location", "description", "date_time", "agent"]
    table([{k: c[k] for k in cols} for c in cs], "No cases.")
    csv_button("Export cases (CSV)", cs, "cases.csv")
    c = pick("Select case", live, lambda c: f"#{c['case_id']} [{c['priority']}] {c['location']} - {c['status']}", "case_sel")
    if not c:
        return
    with st.container(border=True):
        st.markdown(f"**Case #{c['case_id']}** · {c['status']} · tracking `{c['tracking_code']}`")
        st.write(c["description"])
        if c["photo"] and (UPLOAD_DIR / c["photo"]).exists():
            st.image(str(UPLOAD_DIR / c["photo"]), width=300, alt="Photo submitted with the report")
        if c["notes"]:
            st.text(c["notes"].strip())
        if is_coord and c["status"] in ("Reported", "Assigned"):
            ag = pick("Field agent", m.users_by_role("Field Agent"), lambda a: a["name"], "agent_sel")
            if ag and st.button("Assign agent", icon=":material/person_add:"):
                if guard(m.assign_agent, c["case_id"], ag["user_id"], ok="Agent assigned."):
                    auth.audit(user["user_id"], "assign_agent", f"case {c['case_id']} -> {ag['name']}")
                    st.rerun()
        if not is_coord and c["status"] in ("Assigned", "Captured"):
            note = st.text_input("Note (optional)", key="case_note")
            nxt = m.CASE_FLOW[m.CASE_FLOW.index(c["status"]) + 1]
            if st.button(f"Mark as {nxt}", type="primary") and guard(m.advance_case, c["case_id"], note, ok=f"Now {nxt}."):
                st.rerun()
        if c["status"] == "At Centre":
            st.info("Animal has arrived - a vet or caretaker should register it at Intake.")


def release_page():
    user = me()
    role = user["role"]
    st.title(":material/forest: Release & transfer")
    if role == "Veterinarian":
        st.subheader("Release-readiness assessment")
        a = pick("Animal", [x for x in active_animals() if x["current_status"] != "Ready for Release"],
                 animal_fmt, "rel_animal")
        ready = st.toggle("Fit for release / transfer")
        notes = st.text_area("Assessment notes")
        if a and st.button("Save assessment", type="primary"):
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
                auth.audit(user["user_id"], "permit", f"release {r['release_id']}: {permit}")
                st.toast("Permit recorded.")
            outcome = st.segmented_control("Outcome", ["Released", "Sanctuary/Zoo"], default="Released")
            loc = st.text_input("Release / transfer location")
            tag = st.text_input("Tag / GPS collar ID (optional)")
            if st.button("Complete", type="primary"):
                if guard(m.complete_release, r["release_id"], outcome, loc, tag, ok="Done."):
                    auth.audit(user["user_id"], "release", f"{outcome}: animal {r['animal_id']}")
                    st.rerun()
        st.subheader("Track released animals")
        rel = [a for a in m.animals() if a["current_status"] == "Released"]
        a = pick("Released animal", rel, animal_fmt, "trk_animal")
        if a:
            c1, c2 = st.columns(2)
            lat = c1.number_input("Latitude", -90.0, 90.0, 0.0, format="%.5f", key="trk_lat")
            lon = c2.number_input("Longitude", -180.0, 180.0, 0.0, format="%.5f", key="trk_lon")
            note = st.text_input("Sighting note", key="trk_note")
            if st.button("Log sighting"):
                guard(m.add_tracking, a["animal_id"], lat, lon, note, ok="Sighting logged.")
    st.subheader("Completed releases and transfers")
    table(q("""SELECT r.release_id, r.animal_id, a.species, r.permit_no, r.outcome, r.location, r.release_date
               FROM release_record r JOIN animal a USING(animal_id) WHERE r.outcome IS NOT NULL"""))


def staff_page():
    user = me()
    st.title(":material/groups: Staff & volunteers")
    t1, t2, t3, t4 = st.tabs(["Users", "Tasks", "Attendance", "Training"])
    with t1:
        users = m.all_users()
        table(users)
        csv_button("Export users (CSV)", users, "users.csv")
        with st.expander("Create staff account"):
            with st.form("newstaff", clear_on_submit=True):
                name = st.text_input("Name")
                email = st.text_input("Email")
                role = st.selectbox("Role", m.ROLES)
                pw = st.text_input("Temporary password", type="password",
                                   help="They must change it at first login")
                if st.form_submit_button("Create"):
                    try:
                        uid = auth.create_user(name, email, pw, role, must_change=True)
                        auth.audit(user["user_id"], "create_user", f"{email} ({role})")
                        st.success(f"Created user #{uid}.")
                    except ValueError as e:
                        st.error(str(e))
        others = [u for u in users if u["user_id"] != user["user_id"]]
        u = pick("Manage user", others, lambda u: f"{u['name']} ({u['role']}) {'' if u['is_active'] else '[disabled]'}", "mu")
        if u:
            c1, c2 = st.columns(2)
            if c1.button("Disable" if u["is_active"] else "Enable / unlock", width="stretch"):
                m.set_user_active(u["user_id"], not u["is_active"])
                auth.audit(user["user_id"], "toggle_user", u["email"])
                st.rerun()
            with c2.popover("Reset password", width="stretch"):
                tmp = st.text_input("Temporary password", type="password", key="rp")
                if st.button("Reset"):
                    if guard(auth.change_password, u["user_id"], None, tmp, ok="Password reset."):
                        auth.audit(user["user_id"], "reset_password", u["email"])
    with t2:
        v = pick("Volunteer", m.users_by_role("Volunteer"), lambda u: u["name"], "task_vol")
        desc = st.text_input("Task")
        shift = st.segmented_control("Shift", ["Morning", "Afternoon", "Evening", "Night"], default="Morning")
        if v and desc and st.button("Assign task"):
            m.assign_task(v["user_id"], desc, shift or "Morning")
            st.toast("Task assigned.")
        table(m.tasks())
    with t3:
        table(m.attendance(), "No attendance records yet.")
    with t4:
        v = pick("Person", [u for u in m.all_users() if u["role"] != "Donor"], lambda u: u["name"], "tr_user")
        title = st.text_input("Training / certification")
        c1, c2 = st.columns(2)
        done, exp = c1.date_input("Completed on", key="tr_d"), c2.date_input("Expires on", value=None, key="tr_e")
        if v and title and st.button("Add record"):
            m.add_training(v["user_id"], title, done, exp)
            st.toast("Saved.")
        table(m.trainings(), "No training records.")


def inventory_page():
    st.title(":material/inventory_2: Inventory & assets")
    t1, t2 = st.tabs(["Supplies", "Equipment & vehicles"])
    with t1:
        items = q("SELECT * FROM supply_item")
        table([{**i, "low": i["quantity"] <= i["min_level"]} for i in items])
        csv_button("Export (CSV)", items, "inventory.csv")
        i = pick("Item", items, lambda i: f"{i['name']} ({i['quantity']} {i['unit']})", "stock_item")
        delta = st.number_input("Change quantity (+ add / - use)", value=0, step=1)
        if i and st.button("Apply") and guard(m.adjust_stock, i["item_id"], int(delta), ok="Stock updated."):
            st.rerun()
        with st.expander("Add supply item"):
            with st.form("newitem", clear_on_submit=True):
                n = st.text_input("Name")
                ty = st.segmented_control("Type", ["Medical", "Food"], default="Medical")
                qty = st.number_input("Quantity", 0, 100000, 0)
                unit = st.text_input("Unit", "units")
                exp = st.text_input("Expiry (YYYY-MM-DD, optional)")
                mn = st.number_input("Low-stock level", 0, 1000, 5)
                if st.form_submit_button("Add") and n:
                    m.add_item(n, ty or "Medical", qty, unit, exp, mn)
                    st.rerun()
    with t2:
        eq = q("SELECT * FROM equipment")
        table(eq)
        e = pick("Equipment", eq, lambda e: e["name"], "eq_pick")
        s = st.segmented_control("Status", ["Available", "In use", "Under maintenance"], default="Available")
        if e and s and st.button("Update status"):
            m.set_equipment_status(e["equipment_id"], s)
            st.rerun()


def donations_admin_page():
    st.title(":material/volunteer_activism: Donations")
    rows = m.donations()
    table(rows, "No donations yet.")
    if rows:
        st.metric("Total received", f"{sum(r['amount'] for r in rows):.0f}")
        csv_button("Export (CSV)", rows, "donations.csv")


def reports_page():
    st.title(":material/analytics: Reports & audit")
    r = m.report()
    st.subheader("Operational summary")
    table([{"Metric": "Open cases", "Value": r["open_cases"]},
           {"Metric": "Animals admitted", "Value": sum(a["n"] for a in r["animals"])},
           {"Metric": "Donations received", "Value": r["donations"]["n"]},
           {"Metric": "Donation total", "Value": r["donations"]["total"]}])
    csv_button("Export animals (CSV)", m.animals(), "animals.csv")
    st.subheader("Audit log")
    log = m.audit_log()
    table(log, "No activity yet.")
    csv_button("Export audit log (CSV)", log, "audit.csv")


# ---- animals ------------------------------------------------------------
def animals_page():
    st.title(":material/pets: Animals")
    c1, c2 = st.columns([2, 3])
    search = c1.text_input("Search species / tag / ID")
    status = c2.pills("Status", m.ANIMAL_STATUSES, selection_mode="multi")
    rows = m.animals(search=search, statuses=status or None)
    table([{k: a[k] for k in ("animal_id", "species", "tag_id", "age", "gender", "current_status", "enclosure", "intake_date")}
           for a in rows], "No animals match.")
    a = pick("Open profile", rows, animal_fmt, "prof_animal")
    if not a:
        return
    h = m.history(a["animal_id"])
    st.subheader(animal_fmt(a))
    t = st.tabs(["Overview", "Medical", "Daily care", "Release & tracking"])
    with t[0]:
        c = st.columns(4)
        c[0].metric("Age", a["age"])
        c[1].metric("Gender", a["gender"])
        c[2].metric("Enclosure", a["enclosure"] or "-")
        c[3].metric("Admitted", a["intake_date"])
    with t[1]:
        st.markdown("**Diagnoses**")
        table(h["medical"])
        st.markdown("**Treatment plans**")
        table(h["plans"])
        st.markdown("**Surgeries**")
        table(h["surgeries"])
    with t[2]:
        if h["logs"]:
            df = pd.DataFrame(h["logs"]).set_index("date")
            c = st.columns(2)
            c[0].caption("Weight (kg)")
            c[0].line_chart(df["weight"])
            c[1].caption("Temperature (°C)")
            c[1].line_chart(df["temperature"])
        table(h["logs"], "No health logs yet.")
        st.markdown("**Feeding schedule**")
        table(h["feeding"], "No feeding schedule.")
    with t[3]:
        table(h["release"], "Not assessed yet.")
        if h["tracking"]:
            st.map(pd.DataFrame(h["tracking"]), latitude="lat", longitude="lon", size=40)
            table(h["tracking"])


def intake_page():
    st.title(":material/login: Animal intake")
    cs = [c for c in m.cases() if c["status"] == "At Centre"]
    c = pick("From rescue case", [None] + cs,
             lambda c: "Walk-in / no case" if c is None else f"#{c['case_id']} {c['species'] or ''} - {c['location']}",
             "intake_case")
    encl = m.enclosures()
    with st.form("intake", clear_on_submit=True):
        species = st.text_input("Species", value=(c or {}).get("species") or "")
        c1, c2, c3 = st.columns(3)
        age = c1.number_input("Age (years)", 0, 100, 1)
        gender = c2.selectbox("Gender", ["Unknown", "Male", "Female"])
        tag = c3.text_input("Tag ID (optional)")
        e = st.selectbox("Enclosure", encl, format_func=lambda e: (
            f"#{e['enclosure_id']} {e['type']} {e['occupancy']}/{e['capacity']}"
            + (" [quarantine]" if e["quarantine"] else "")))
        if st.form_submit_button("Register animal", type="primary"):
            if not species.strip():
                st.error("Species is required.")
            else:
                try:
                    aid = m.register_animal(species.strip(), age, gender, e["enclosure_id"],
                                            c["case_id"] if c else None, tag.strip())
                    st.success(f"Animal #{aid} admitted.")
                except m.RuleError as err:
                    st.error(str(err))
    st.subheader("Move to another enclosure")
    a = pick("Animal", active_animals(), animal_fmt, "mv_animal")
    e2 = pick("New enclosure", encl, lambda e: f"#{e['enclosure_id']} {e['type']} {e['occupancy']}/{e['capacity']}"
              + (" [quarantine]" if e["quarantine"] else ""), "mv_enc")
    if a and e2 and st.button("Move"):
        guard(m.assign_enclosure, a["animal_id"], e2["enclosure_id"], ok="Animal moved.")
    with st.expander("Add enclosure"):
        with st.form("newenc", clear_on_submit=True):
            ty = st.text_input("Type")
            cap = st.number_input("Capacity", 1, 100, 2)
            loc = st.text_input("Location")
            qn = st.toggle("Quarantine enclosure")
            if st.form_submit_button("Add") and ty:
                m.add_enclosure(ty, cap, loc, qn)
                st.rerun()


# ---- vet ----------------------------------------------------------------
def medical_page():
    user = me()
    st.title(":material/medical_services: Medical care")
    a = pick("Animal", active_animals(), animal_fmt, "med_animal")
    if not a:
        return
    t1, t2, t3 = st.tabs(["Diagnose", "Treatment plan", "Surgery"])
    with t1:
        with st.form("diag", clear_on_submit=True):
            dx = st.text_input("Diagnosis")
            notes = st.text_area("Exam notes")
            if st.form_submit_button("Save medical record") and dx.strip():
                m.add_diagnosis(a["animal_id"], user["user_id"], dx.strip(), notes)
                st.success("Saved - animal marked Under Treatment.")
        table(m.history(a["animal_id"])["medical"])
    with t2:
        with st.form("plan", clear_on_submit=True):
            med = st.text_input("Medication / treatment")
            sched = st.text_input("Schedule (e.g. twice daily)")
            c1, c2 = st.columns(2)
            start, end = c1.date_input("Start"), c2.date_input("End")
            if st.form_submit_button("Create plan") and med.strip():
                guard(m.create_plan, a["animal_id"], user["user_id"], med.strip(), sched, start, end,
                      ok="Treatment plan created.")
        plans = m.history(a["animal_id"])["plans"]
        table(plans)
        p = pick("Mark plan completed", [p for p in plans if p["status"] == "Active"],
                 lambda p: f"#{p['plan_id']} {p['medication']}", "done_plan")
        if p and st.button("Mark completed"):
            m.complete_plan(p["plan_id"])
            st.rerun()
    with t3:
        with st.form("surg", clear_on_submit=True):
            proc = st.text_input("Procedure")
            c1, c2 = st.columns(2)
            d, tm = c1.date_input("Date", key="sd"), c2.time_input("Time", key="st")
            if st.form_submit_button("Schedule surgery") and proc.strip():
                m.schedule_surgery(a["animal_id"], user["user_id"], f"{d} {tm.strftime('%H:%M')}", proc.strip())
                st.toast("Surgery scheduled.")
        surg = m.history(a["animal_id"])["surgeries"]
        table(surg, "No surgeries.")
        s = pick("Update surgery", [s for s in surg if s["status"] == "Scheduled"],
                 lambda s: f"#{s['surgery_id']} {s['procedure']} {s['scheduled_at']}", "surg_sel")
        if s:
            res = st.segmented_control("Outcome", ["Completed", "Cancelled"], default="Completed")
            sn = st.text_input("Notes", key="surg_notes")
            if st.button("Update") and res:
                m.update_surgery(s["surgery_id"], res, sn)
                st.rerun()


# ---- caretaker ----------------------------------------------------------
def care_page():
    user = me()
    st.title(":material/volunteer_activism: Daily care")
    t1, t2 = st.tabs(["Health log", "Feeding schedule"])
    with t1:
        a = pick("Animal", active_animals(), animal_fmt, "care_animal")
        if a:
            with st.form("log", clear_on_submit=True):
                c1, c2 = st.columns(2)
                w = c1.number_input("Weight (kg)", 0.0, 2000.0, 0.0, 0.1)
                t = c2.number_input("Temperature (°C)", 0.0, 50.0, 37.0, 0.1)
                beh = st.segmented_control("Behaviour", ["Calm", "Active", "Lethargic", "Aggressive", "Stressed", "Not eating"],
                                           default="Calm")
                feed = st.text_input("Feeding given")
                rem = st.text_area("Remarks")
                if st.form_submit_button("Add log", type="primary"):
                    m.add_health_log(a["animal_id"], user["user_id"], w, t, beh or "Calm", feed, rem)
                    st.toast("Logged. Vets are alerted automatically if the animal looks unwell.")
            h = m.history(a["animal_id"])
            st.markdown("**Active treatment plans**")
            table([p for p in h["plans"] if p["status"] == "Active"], "No active plans.")
            if h["logs"]:
                st.line_chart(pd.DataFrame(h["logs"]).set_index("date")[["weight", "temperature"]])
            table(list(reversed(h["logs"])), "No logs yet.")
    with t2:
        st.markdown("**Today's feeding**")
        due = m.feeding_today()
        if not due:
            st.info("No feeding schedule yet.")
        for f in due:
            c = st.columns([4, 1], vertical_alignment="center")
            c[0].markdown(f"{'~~' if f['fed'] else ''}#{f['animal_id']} {f['species']} - {f['meal_time']}: "
                          f"{f['food']} ({f['quantity']}){'~~' if f['fed'] else ''}")
            if not f["fed"] and c[1].button("Fed", key=f"fed{f['feed_id']}"):
                m.mark_fed(f["feed_id"])
                st.rerun()
        a2 = pick("Add schedule for", active_animals(), animal_fmt, "feed_animal")
        if a2:
            with st.form("feedform", clear_on_submit=True):
                mt = st.time_input("Meal time")
                food = st.text_input("Food")
                qty = st.text_input("Quantity")
                if st.form_submit_button("Add") and food:
                    m.add_feeding(a2["animal_id"], mt.strftime("%H:%M"), food, qty)
                    st.rerun()


# ---- volunteer ----------------------------------------------------------
def my_tasks_page():
    user = me()
    st.title(":material/task_alt: My tasks")
    rows = m.tasks(user["user_id"])
    table([{k: r[k] for k in ("task_id", "description", "shift", "status")} for r in rows], "No tasks assigned.")
    t = pick("Task", [r for r in rows if r["status"] != "Done"], lambda t: f"#{t['task_id']} {t['description']}", "my_task")
    status = st.segmented_control("Status", ["In progress", "Done"], default="In progress")
    if t and status and st.button("Update"):
        m.update_task(t["task_id"], status)
        st.rerun()


def attendance_page():
    user = me()
    st.title(":material/schedule: Attendance & training")
    open_ = m.open_attendance(user["user_id"])
    if open_:
        st.success(f"Checked in since {open_['check_in']}")
        if st.button("Check out", type="primary"):
            m.check_out(user["user_id"])
            st.rerun()
    elif st.button("Check in", type="primary"):
        m.check_in(user["user_id"])
        st.rerun()
    st.subheader("My attendance")
    table(m.attendance(user["user_id"]), "No records yet.")
    st.subheader("My training & certificates")
    table(m.trainings(user["user_id"]), "No training recorded.")


# ---- donor --------------------------------------------------------------
def donate_page():
    user = me()
    st.title(":material/favorite: Donate")
    with st.form("don", clear_on_submit=True):
        ty = st.segmented_control("Type", ["Money", "Supplies"], default="Money")
        amt = st.number_input("Amount / estimated value", 0.0, step=100.0)
        purpose = st.text_input("Purpose", placeholder="Medicine, food, enclosure repair...")
        if st.form_submit_button("Donate", type="primary"):
            try:
                receipt = m.donate(user["user_id"], amt, ty or "Money", purpose)
                st.success(f"Thank you! Receipt {receipt}")
            except m.RuleError as e:
                st.error(str(e))


def my_donations_page():
    user = me()
    st.title(":material/receipt_long: My donations")
    rows = m.donations(user["user_id"])
    table(rows, "No donations yet.")
    if rows:
        st.metric("Total given", f"{sum(r['amount'] for r in rows):.0f}")
        r = st.selectbox("Receipt", rows, format_func=lambda r: f"{r['receipt_no']} - {r['date']} - {r['amount']:.0f}")
        text = (f"DONATION RECEIPT\nReceipt: {r['receipt_no']}\nDate: {r['date']}\nDonor: {user['name']}\n"
                f"Type: {r['type']}\nAmount: {r['amount']:.2f}\nPurpose: {r['purpose'] or 'General'}\n"
                f"Thank you for supporting wildlife rescue.\n")
        st.download_button("Download receipt", text, f"{r['receipt_no']}.txt", icon=":material/download:")
