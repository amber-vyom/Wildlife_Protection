# Wildlife Rescue & Rehabilitation Management System

Streamlit + SQLite implementation of the Review-1 design (use cases and class diagram).

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```
The database (`wildlife.db`) is created and seeded on first run.

## Demo logins
| Role | Email | Password |
|---|---|---|
| Coordinator | coordinator@wild.org | coord123 |
| Field Agent | agent@wild.org | agent123 |
| Veterinarian | vet@wild.org | vet123 |
| Caretaker | caretaker@wild.org | care123 |
| Volunteer | volunteer@wild.org | vol123 |
| Donor | donor@wild.org | donor123 |

Citizens report animals from the login page without an account.

## Walkthrough
1. Citizen reports an animal (public tab).
2. Coordinator assigns a field agent (Rescue cases).
3. Field agent advances the case: Assigned → Captured → At Centre.
4. Vet or caretaker registers the animal at Intake (case closes).
5. Vet diagnoses and creates a treatment plan; caretaker adds daily health logs.
6. Vet completes the plan and assesses release readiness.
7. Coordinator records the Forest Department permit and completes release or transfer.

## Layout
- `db.py` - schema, helpers, seed data
- `models.py` - business rules (controllers + entities)
- `app.py` - Streamlit UI, role-based menus
