---
title: Wildlife Rescue
emoji: 🦉
colorFrom: green
colorTo: green
sdk: streamlit
sdk_version: 1.66.1
python_version: "3.12"
app_file: app.py
pinned: false
---

# Wildlife Rescue & Rehabilitation Management System

A multi-page Streamlit site (SQLite backend) built from the Review-1 use cases and class diagram.

## Run
```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```
The database (`wildlife.db`) is created and seeded on first run. If you have a database from the
earlier version, it is rebuilt automatically (demo data only).

## Accounts
Anyone can sign up as a **Donor** or **Volunteer**. Staff accounts are created by a Coordinator
(Staff & volunteers → Create staff account) and must change their temporary password at first sign-in.

Demo accounts:

| Role | Email | Password |
|---|---|---|
| Coordinator | coordinator@wild.org | Coord@123 |
| Field Agent | agent@wild.org | Agent@123 |
| Veterinarian | vet@wild.org | Vet@1234 |
| Caretaker | caretaker@wild.org | Care@123 |
| Volunteer | volunteer@wild.org | Volun@123 |
| Donor | donor@wild.org | Donor@123 |

## Login & security
- Salted PBKDF2-SHA256 password hashing (200k iterations), constant-time comparison
- Password policy (8+ chars, letters and digits), email validation
- Account lockout for 10 minutes after 5 failed attempts
- 30-minute inactivity timeout; disabled accounts are signed out immediately
- Forced password change for coordinator-created accounts and admin resets
- Audit log of logins, lockouts, assignments, permits, releases and user changes
- Sign-in is local (email + password). Sessions end on browser refresh.

## Features
**Public:** home with live stats, report an animal (urgency, map coordinates, photo, no personal data),
tracking code to follow a report, success stories.

**Coordinator:** dashboard with charts, prioritised case list with map and agent assignment, animals,
release permits and post-release tracking, user management, tasks, training, attendance, inventory
and equipment, donations, reports, CSV exports, audit log.

**Field agent:** assigned cases, progress updates (Assigned → Captured → At Centre).

**Veterinarian:** animal profiles, intake, diagnoses, treatment plans, surgery scheduling,
release-readiness assessment.

**Caretaker:** health logs with weight/temperature charts, daily feeding schedule, intake, inventory.
Unwell readings alert the vets automatically.

**Volunteer:** task list, check-in/out attendance, training record.

**Donor:** donate, history, downloadable receipts.

All roles get in-app notifications and a profile page.

## Business rules
- A case cannot advance until an agent is assigned; closing happens at intake.
- Enclosure capacity cannot be exceeded.
- No release-ready mark while a treatment plan is active or a surgery is scheduled.
- Release needs a Forest Department permit number; only released animals can be tracked.

## Layout
- `app.py` - navigation, session checks, role-based menus
- `views.py` - all pages
- `models.py` - business rules (controllers + entities)
- `auth.py` - hashing, lockout, signup, audit
- `db.py` - schema, helpers, seed data
- `.streamlit/config.toml` - theme
