"""Wildlife Rescue & Rehabilitation Management System - Streamlit site.

Run:  streamlit run app.py
"""
from datetime import datetime, timedelta

import streamlit as st

import auth
import models as m
import views as v
from db import init_db

SESSION_TIMEOUT = timedelta(minutes=30)

st.set_page_config(page_title="Wildlife Rescue", page_icon=":material/pets:", layout="wide",
                   menu_items={"Get help": None, "Report a bug": None, "About": "Wildlife Rescue & Rehabilitation Management System"})

# Hide the hosting toolbar (Fork / GitHub / Share) so visitors only see the app
st.html("<style>[data-testid='stToolbar'], [data-testid='stAppDeployButton'], [data-testid='stToolbarActions'], "
        ".stAppToolbar a[href*='github.com'], ._profileContainer_gzau3_53, ._container_gzau3_1 { display:none !important; }</style>")
init_db()


def logout(reason: str | None = None):
    u = st.session_state.pop("user", None)
    if u:
        auth.audit(u["user_id"], "logout", reason or "")
    st.session_state.pop("last_active", None)
    if reason:
        st.session_state["flash"] = reason


def P(fn, title, icon, path, default=False):
    return st.Page(fn, title=title, icon=f":material/{icon}:", url_path=path, default=default)


# ---- session checks -----------------------------------------------------
user = st.session_state.get("user")
if user:
    fresh = m.get_user(user["user_id"])
    last = st.session_state.get("last_active")
    if not fresh or not fresh["is_active"]:
        logout("Your account is no longer active.")
        user = None
    elif last and datetime.now() - last > SESSION_TIMEOUT:
        logout("You were signed out after 30 minutes of inactivity.")
        user = None
    else:
        user = st.session_state["user"] = fresh
        st.session_state["last_active"] = datetime.now()

# ---- pages --------------------------------------------------------------
home = P(v.home, "Home", "home", "home", default=not user)
report = P(v.report_page, "Report an animal", "report", "report")
track = P(v.track_page, "Track a report", "search", "track")
stories = P(v.stories_page, "Success stories", "forest", "stories")
login = P(v.login_page, "Sign in", "login", "login")
signup = P(v.signup_page, "Create account", "person_add", "signup")
v.PAGE.update(report=report, track=track, signup=signup)

if not user:
    nav = st.navigation({"Public": [home, report, track, stories], "Account": [login, signup]})
elif user["must_change_pw"]:
    nav = st.navigation([P(v.force_password_page, "Set new password", "lock_reset", "password", True)],
                        position="hidden")
else:
    unread = m.unread_count(user["user_id"])
    notif = P(v.notifications_page, f"Notifications ({unread})" if unread else "Notifications",
              "notifications", "notifications")
    prof = P(v.profile_page, "My profile", "account_circle", "profile")
    animals = P(v.animals_page, "Animals", "pets", "animals")
    intake = P(v.intake_page, "Intake", "login", "intake")
    inventory = P(v.inventory_page, "Inventory", "inventory_2", "inventory")
    cases = P(v.cases_page, "Rescue cases" if user["role"] == "Coordinator" else "My cases", "emergency", "cases")
    release = P(v.release_page, "Release", "forest", "release")
    role_pages = {
        "Coordinator": [P(v.dashboard_page, "Dashboard", "dashboard", "dashboard", True), cases, animals, release,
                        P(v.staff_page, "Staff & volunteers", "groups", "staff"), inventory,
                        P(v.donations_admin_page, "Donations", "volunteer_activism", "donations"),
                        P(v.reports_page, "Reports", "analytics", "reports"),
                        P(v.audit_page, "Audit log", "policy", "audit")],
        "Field Agent": [P(v.cases_page, "My cases", "emergency", "cases", True)],
        "Veterinarian": [P(v.animals_page, "Animals", "pets", "animals", True), intake,
                         P(v.medical_page, "Medical care", "medical_services", "medical"), release],
        "Caretaker": [P(v.animals_page, "Animals", "pets", "animals", True), intake,
                      P(v.care_page, "Daily care", "volunteer_activism", "care"), inventory],
        "Volunteer": [P(v.my_tasks_page, "My tasks", "task_alt", "tasks", True),
                      P(v.attendance_page, "Attendance & training", "schedule", "attendance")],
        "Donor": [P(v.donate_page, "Donate", "favorite", "donate", True),
                  P(v.my_donations_page, "My donations", "receipt_long", "my-donations")],
    }
    nav = st.navigation({user["role"]: role_pages[user["role"]], "Account": [notif, prof]})

# ---- sidebar ------------------------------------------------------------
with st.sidebar:
    if user:
        st.markdown(f"**{user['name']}**  \n{user['role']}")
        if st.button("Sign out", icon=":material/logout:", width="stretch"):
            logout()
            st.rerun()
if flash := st.session_state.pop("flash", None):
    st.warning(flash)

nav.run()
