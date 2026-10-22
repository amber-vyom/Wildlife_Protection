"""Authentication: salted PBKDF2 hashing, password policy, lockout, audit trail."""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

from db import q, x

ITERATIONS = 200_000
MAX_FAILS = 5
LOCK_MINUTES = 10
SELF_SIGNUP_ROLES = ["Donor", "Volunteer"]  # staff roles are created by a Coordinator
FMT = "%Y-%m-%d %H:%M:%S"


def _hash(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), ITERATIONS).hex()


def make_credentials(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    return _hash(password, salt), salt


def password_problem(pw: str) -> str | None:
    if len(pw) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Password must contain letters and digits."
    return None


def email_ok(email: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()))


def audit(user_id, action: str, detail: str = "") -> None:
    x("INSERT INTO audit_log(ts,user_id,action,detail) VALUES(?,?,?,?)",
      (datetime.now().strftime(FMT), user_id, action, detail))


def authenticate(email: str, password: str) -> tuple[dict | None, str]:
    """Return (user, message). Same generic error for unknown email / wrong password."""
    rows = q("SELECT * FROM users WHERE email=?", (email.strip().lower(),))
    if not rows:
        _hash(password, "00" * 16)  # keep timing similar
        return None, "Invalid email or password."
    u = rows[0]
    now = datetime.now()
    if u["locked_until"] and datetime.strptime(u["locked_until"], FMT) > now:
        mins = int((datetime.strptime(u["locked_until"], FMT) - now).total_seconds() // 60) + 1
        return None, f"Account locked after too many failed attempts. Try again in {mins} min."
    if not u["is_active"]:
        return None, "This account has been disabled. Contact the coordinator."
    if not hmac.compare_digest(_hash(password, u["salt"]), u["password_hash"]):
        fails = u["failed_attempts"] + 1
        if fails >= MAX_FAILS:
            x("UPDATE users SET failed_attempts=0, locked_until=? WHERE user_id=?",
              ((now + timedelta(minutes=LOCK_MINUTES)).strftime(FMT), u["user_id"]))
            audit(u["user_id"], "lockout", email)
        else:
            x("UPDATE users SET failed_attempts=? WHERE user_id=?", (fails, u["user_id"]))
        return None, "Invalid email or password."
    x("UPDATE users SET failed_attempts=0, locked_until=NULL, last_login=? WHERE user_id=?",
      (now.strftime("%Y-%m-%d %H:%M"), u["user_id"]))
    audit(u["user_id"], "login")
    return u, ""


def create_user(name, email, password, role, phone="", skills="", must_change=False) -> int:
    email = email.strip().lower()
    if not name.strip():
        raise ValueError("Name is required.")
    if not email_ok(email):
        raise ValueError("Enter a valid email address.")
    if (p := password_problem(password)):
        raise ValueError(p)
    if q("SELECT 1 FROM users WHERE email=?", (email,)):
        raise ValueError("That email is already registered.")
    h, s = make_credentials(password)
    return x("""INSERT INTO users(name,email,password_hash,salt,role,phone,skills,must_change_pw,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
             (name.strip(), email, h, s, role, phone, skills, int(must_change),
              datetime.now().strftime("%Y-%m-%d %H:%M")))


def change_password(user_id: int, old: str | None, new: str) -> None:
    """old=None skips the old-password check (admin reset)."""
    u = q("SELECT * FROM users WHERE user_id=?", (user_id,))[0]
    if old is not None and not hmac.compare_digest(_hash(old, u["salt"]), u["password_hash"]):
        raise ValueError("Current password is incorrect.")
    if (p := password_problem(new)):
        raise ValueError(p)
    h, s = make_credentials(new)
    x("UPDATE users SET password_hash=?, salt=?, must_change_pw=? WHERE user_id=?",
      (h, s, 1 if old is None else 0, user_id))
    audit(user_id, "password_change" if old is not None else "password_reset")
