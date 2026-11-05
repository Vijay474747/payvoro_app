"""
Payvoro core logic – plain Python (no web framework here, so it is easy to test).
Database: Neon Postgres on Vercel (DATABASE_URL), or a SQLite file on your PC.

Settings (environment variables):
  DATABASE_URL            Postgres URL (Vercel -> Storage -> Neon sets it for you)
  PAYVORO_DB              SQLite file when DATABASE_URL is not set (default payvoro.db)
  PAYVORO_DEV=1           test mode: login token "dev:<email>" works without Google (never use live!)
  ALLOW_SIGNUP=1          any Google account can sign up (0 = only emails you added in admin)
  TRIAL_DAYS=3            free days after the merchant sets UPI AutoPay (first plan only)
  GOOGLE_WEB_CLIENT_ID    Google Cloud -> OAuth client ID (Web application). Same value as in the app.
  RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET   Razorpay API keys (AutoPay made by the server, best)
  RAZORPAY_PLAN_BASIC     Razorpay Subscription plan ID (Rs 30 monthly)
  RAZORPAY_WEBHOOK_SECRET  webhook secret (https://YOUR_DOMAIN/api/razorpay/webhook)
  RAZORPAY_LINK_BASIC     your AutoPay link from the dashboard (used when API keys are not set;
                          the merchant must use the same email as their Google login)
  RAZORPAY_ME_LINK        backup "pay by link" page (razorpay.me) - you approve these on the admin page
  CRON_SECRET             Vercel Cron sends it: the daily AutoPay check (/api/cron/autopay-sync)
"""
import base64
import copy
import datetime as _dt
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from typing import Optional

import database
import legal_pages

log = logging.getLogger("payvoro")

DB_PATH = os.getenv("PAYVORO_DB", "payvoro.db")
DEV = os.getenv("PAYVORO_DEV", "0") == "1"
ALLOW_SIGNUP = os.getenv("ALLOW_SIGNUP", "1") == "1"
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "3"))
GRACE_DAYS = 3
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_WEB_CLIENT_ID", "")
RAZORPAY_ME_LINK = os.getenv("RAZORPAY_ME_LINK", "https://razorpay.me/@payvoro_sound_box_app")

DAY_MS = 86_400_000

# The app SHOWS the per-day price. Razorpay CHARGES the monthly price by UPI AutoPay.
PLANS = {
    "basic": {
        "id": "basic", "name": "Basic", "price": 30, "per_day": "1", "days": 30,
        "features": ["Voice alert in Tamil (தமிழ்) or English", "All UPI apps + bank SMS",
                     "Scan & show your shop QR", "30 days payment history (saved only on your phone)"],
        "flags": {"languages": ["ta", "en"], "say_name": False, "analytics": False, "history_days": 30},
        "rzp_plan_id": os.getenv("RAZORPAY_PLAN_BASIC", ""),
        "link": os.getenv("RAZORPAY_LINK_BASIC", "https://rzp.io/rzp/WO6mEyFr"),
    },
    # The Plus plan was removed (Razorpay review). Old "plus" accounts are treated as Basic.
}
PUBLIC_PLAN_KEYS = ("id", "name", "price", "per_day", "days", "features", "flags")


MAX_PRICE = 15000          # UPI AutoPay limit without extra approval (Rs)


def per_day_text(price: int) -> str:
    """30 -> '1', 60 -> '2', 54 -> '1.8'"""
    t = f"{price / 30:.1f}"
    return t[:-2] if t.endswith(".0") else t


def get_plans(c=None) -> dict:
    """The plan is FIXED in the code (PLANS above). The admin page only shows it; it can't change it.
    To change the price or link: edit PLANS, or set RAZORPAY_LINK_BASIC / RAZORPAY_PLAN_BASIC on Vercel.
    (Old prices saved in the plan_settings table are ignored.)"""
    return copy.deepcopy(PLANS)


def public_plans(c=None) -> list:
    return [{k: p[k] for k in PUBLIC_PLAN_KEYS} for p in get_plans(c).values()]


def _plan_for_rzp_id(c, plans: dict, rzp_plan_id: Optional[str]) -> Optional[str]:
    """Which Payvoro plan is this Razorpay plan_id? Also knows old plan IDs from before a price change."""
    if not rzp_plan_id:
        return None
    for k, p in plans.items():
        if p["rzp_plan_id"] and p["rzp_plan_id"] == rzp_plan_id:
            return k
    r = c.execute("SELECT plan FROM rzp_plans WHERE rzp_plan_id=?", (rzp_plan_id,)).fetchone()
    return r["plan"] if r and r["plan"] in plans else None


class AppError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def now_ms() -> int:
    return int(time.time() * 1000)


# ---------------- database ----------------
@contextmanager
def db():
    with database.connect(DB_PATH) as conn:
        yield conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS merchants(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    phone TEXT UNIQUE,
    upi_id TEXT,
    city TEXT,
    plan TEXT NOT NULL DEFAULT 'none',
    plan_until INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    last_seen INTEGER,
    google_sub TEXT UNIQUE,
    email TEXT,
    autopay_ref TEXT,
    autopay_status TEXT NOT NULL DEFAULT '',
    trial_used INTEGER NOT NULL DEFAULT 0,
    on_trial INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    message TEXT,
    autopay_checked_at INTEGER
);
CREATE TABLE IF NOT EXISTS sessions(
    token_hash TEXT PRIMARY KEY,
    merchant_id INTEGER NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    device TEXT,
    created_at INTEGER NOT NULL,
    last_seen INTEGER
);
CREATE TABLE IF NOT EXISTS events(
    id TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS payments(
    id INTEGER PRIMARY KEY,
    merchant_id INTEGER NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    amount REAL NOT NULL,
    payer TEXT,
    app TEXT,
    status TEXT,
    ts INTEGER NOT NULL,
    dedupe_key TEXT NOT NULL,
    received_at INTEGER NOT NULL,
    utr TEXT,
    source TEXT NOT NULL DEFAULT 'app',
    bank_confirmed INTEGER NOT NULL DEFAULT 0,
    UNIQUE(merchant_id, dedupe_key)
);
CREATE INDEX IF NOT EXISTS idx_pay_merchant_ts ON payments(merchant_id, ts);
CREATE TABLE IF NOT EXISTS plan_settings(
    plan_id TEXT PRIMARY KEY,
    price INTEGER NOT NULL,
    rzp_plan_id TEXT,
    link TEXT,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS rzp_plans(
    rzp_plan_id TEXT PRIMARY KEY,
    plan TEXT NOT NULL,
    amount INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS subscriptions(
    id INTEGER PRIMARY KEY,
    merchant_id INTEGER NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    plan TEXT NOT NULL,
    amount INTEGER NOT NULL,
    method TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    provider_ref TEXT,
    payment_ref TEXT,
    created_at INTEGER NOT NULL,
    paid_at INTEGER,
    trial INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS charges(
    id INTEGER PRIMARY KEY,
    merchant_id INTEGER NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    subscription_id INTEGER,
    amount INTEGER NOT NULL,
    method TEXT NOT NULL,
    payment_ref TEXT,
    paid_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_charges_paid ON charges(paid_at);
CREATE TABLE IF NOT EXISTS admin_log(
    id INTEGER PRIMARY KEY,
    created_at INTEGER NOT NULL,
    merchant_id INTEGER,
    action TEXT NOT NULL,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at INTEGER NOT NULL
);
"""

MERCHANT_COLS = ["id", "name", "phone", "upi_id", "city", "plan", "plan_until", "active", "created_at", "last_seen",
                 "google_sub", "email", "autopay_ref", "autopay_status", "trial_used", "on_trial", "notes", "message",
                 "autopay_checked_at"]


def _upgrade_merchants(c):
    """Old databases (OTP login) had phone NOT NULL. Google login needs phone to be optional."""
    info = {r["name"]: r for r in c.execute("PRAGMA table_info(merchants)")}
    if info and info["phone"]["notnull"] == 0 and "on_trial" in info:
        return
    old_cols = [k for k in info if k in MERCHANT_COLS]
    c.execute("PRAGMA foreign_keys = OFF")
    c.execute("PRAGMA legacy_alter_table = ON")      # keep other tables pointing at "merchants"
    c.execute("ALTER TABLE merchants RENAME TO merchants_old")
    c.executescript(SCHEMA)
    cols = ", ".join(old_cols)
    c.execute(f"INSERT INTO merchants({cols}) SELECT {cols} FROM merchants_old")
    c.execute("DROP TABLE merchants_old")
    c.execute("PRAGMA legacy_alter_table = OFF")


def init_db():
    _init_tables()
    import autopay_sync          # AutoPay check from Razorpay (its own table + merchants.autopay_checked_at)
    autopay_sync.init_db()


def _init_tables():
    with db() as c:
        if c.pg:
            # Two Vercel instances may start at the same moment: only one creates the tables.
            c.execute("SELECT pg_advisory_xact_lock(724001)")
            c.executescript(database.to_postgres_schema(SCHEMA))
            c.execute("CREATE INDEX IF NOT EXISTS idx_sub_ref ON subscriptions(provider_ref)")
            c.execute("ALTER TABLE merchants ADD COLUMN IF NOT EXISTS notes TEXT")
            c.execute("ALTER TABLE merchants ADD COLUMN IF NOT EXISTS message TEXT")
            _backfill_charges(c)
            return
        c.executescript(SCHEMA)
        # upgrade older databases
        cols = {r["name"] for r in c.execute("PRAGMA table_info(payments)")}
        for name, ddl in (("utr", "TEXT"), ("source", "TEXT NOT NULL DEFAULT 'app'"),
                          ("bank_confirmed", "INTEGER NOT NULL DEFAULT 0")):
            if name not in cols:
                c.execute(f"ALTER TABLE payments ADD COLUMN {name} {ddl}")
        sub_cols = {r["name"] for r in c.execute("PRAGMA table_info(subscriptions)")}
        if "trial" not in sub_cols:
            c.execute("ALTER TABLE subscriptions ADD COLUMN trial INTEGER NOT NULL DEFAULT 0")
        _upgrade_merchants(c.raw)
        m_cols = {r["name"] for r in c.execute("PRAGMA table_info(merchants)")}
        for name in ("notes", "message"):
            if name not in m_cols:
                c.execute(f"ALTER TABLE merchants ADD COLUMN {name} TEXT")
        c.execute("DROP TABLE IF EXISTS otps")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sub_ref ON subscriptions(provider_ref)")
        _backfill_charges(c)


def _backfill_charges(c):
    """v4.1: every payment from a merchant is a row in "charges" (before, a monthly AutoPay charge overwrote
    the last one). Once, copy the paid requests we already have, so the income chart is not empty."""
    if c.execute("SELECT 1 FROM settings WHERE key='charges_backfilled'").fetchone():
        return
    c.execute("INSERT INTO charges(merchant_id, subscription_id, amount, method, payment_ref, paid_at)"
              " SELECT merchant_id, id, amount, method, payment_ref, COALESCE(paid_at, created_at)"
              " FROM subscriptions WHERE status='paid'")
    c.execute("INSERT INTO settings(key, value, updated_at) VALUES ('charges_backfilled', '1', ?)", (now_ms(),))


# ---------------- helpers ----------------
_VPA = re.compile(r"^[A-Za-z0-9.\-_]{2,256}@[A-Za-z][A-Za-z0-9]{1,63}$")


def valid_vpa(v: str) -> bool:
    return bool(_VPA.match(v or ""))


def normalize_phone(raw: str) -> str:
    d = re.sub(r"\D", "", raw or "")
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    if not re.fullmatch(r"[6-9]\d{9}", d):
        raise AppError(400, "Enter a valid 10-digit mobile number")
    return d


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _http_json(req: urllib.request.Request, timeout=15) -> dict:
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def plan_flags(plan: str) -> dict:
    # Only one plan now. Old "trial" / "plus" accounts get the Basic features.
    return PLANS.get(plan, PLANS["basic"])["flags"]


def public_merchant(m) -> dict:
    now = now_ms()
    active = bool(m["active"]) and m["plan_until"] > now
    return {
        "id": m["id"], "name": m["name"], "phone": m["phone"], "email": m["email"] or "",
        "upi_id": m["upi_id"], "city": m["city"],
        "plan": m["plan"], "plan_until": m["plan_until"], "plan_active": active,
        "on_trial": bool(m["on_trial"]) and active,
        "autopay": m["autopay_status"] in ("authenticated", "active"),
        "autopay_status": m["autopay_status"] or "",
        # True = never had a plan: the app shows the plans page before Home
        "needs_plan": m["plan_until"] == 0 and not m["autopay_status"],
        "can_announce": bool(m["active"]) and m["plan_until"] + GRACE_DAYS * DAY_MS > now,
        "grace_days": GRACE_DAYS, "trial_days": TRIAL_DAYS, "flags": plan_flags(m["plan"]),
    }


# ---------------- Google login ----------------
def verify_google_token(id_token: str) -> dict:
    """Checks the Google ID token from the app. Returns {sub, email, name}."""
    if DEV and id_token.startswith("dev:"):                 # test mode only
        email = id_token[4:].strip().lower()
        return {"sub": "dev-" + email, "email": email, "name": email.split("@")[0]}
    if not GOOGLE_CLIENT_ID:
        raise AppError(500, "Server: GOOGLE_WEB_CLIENT_ID is not set")
    from google.oauth2 import id_token as gid
    from google.auth.transport import requests as greq
    try:
        # clock_skew: Vercel / phone clocks can be a few seconds off → "Token used too early"
        info = gid.verify_oauth2_token(id_token, greq.Request(), GOOGLE_CLIENT_ID, clock_skew_in_seconds=30)
    except Exception as e:
        reason = str(e)
        log.warning("Google token check failed: %s", reason)   # see it in Vercel → Logs
        if "audience" in reason.lower():
            raise AppError(401, "Server: GOOGLE_WEB_CLIENT_ID on the server is not the same as in the app.")
        raise AppError(401, "Google login could not be checked. Please try again.")
    if not info.get("email_verified"):
        raise AppError(401, "Your Google email is not verified")
    return {"sub": info["sub"], "email": info.get("email", "").lower(), "name": info.get("name", "")}


def login_google(id_token: str, device: Optional[str] = None) -> dict:
    g = verify_google_token(id_token)
    now = now_ms()
    with db() as c:
        m = c.execute("SELECT * FROM merchants WHERE google_sub=?", (g["sub"],)).fetchone()
        if m is None and g["email"]:
            # A merchant you added on the admin page by email: link the Google account to it
            m = c.execute("SELECT * FROM merchants WHERE lower(email)=? AND google_sub IS NULL", (g["email"],)).fetchone()
            if m is not None:
                c.execute("UPDATE merchants SET google_sub=? WHERE id=?", (g["sub"], m["id"]))
        if m is None:
            if not ALLOW_SIGNUP:
                raise AppError(403, "This Google account is not registered. Please contact Payvoro.")
            mid = c.insert(
                "INSERT INTO merchants(google_sub, email, plan, plan_until, created_at) VALUES (?,?,'none',0,?)",
                (g["sub"], g["email"], now),
            )
        else:
            mid = m["id"]
            c.execute("UPDATE merchants SET email=? WHERE id=?", (g["email"], mid))
        m = c.execute("SELECT * FROM merchants WHERE id=?", (mid,)).fetchone()
        if not m["active"]:
            raise AppError(403, "Your account is stopped. Please contact Payvoro.")

        token = secrets.token_urlsafe(32)
        c.execute("INSERT INTO sessions(token_hash, merchant_id, device, created_at, last_seen) VALUES (?,?,?,?,?)",
                  (_token_hash(token), mid, (device or "")[:80], now, now))
        c.execute("UPDATE merchants SET last_seen=? WHERE id=?", (now, mid))
    return {"token": token, "is_new": not (m["name"] and m["upi_id"]), "google_name": g["name"],
            "merchant": public_merchant(m)}


def merchant_by_token(token: str):
    if not token:
        raise AppError(401, "Please log in")
    th = _token_hash(token)
    now = now_ms()
    with db() as c:
        m = c.execute(
            "SELECT m.* FROM sessions s JOIN merchants m ON m.id = s.merchant_id WHERE s.token_hash=?", (th,)
        ).fetchone()
        if not m:
            raise AppError(401, "Session expired. Please log in again.")
        if not m["active"]:
            raise AppError(403, "Your account is stopped. Please contact Payvoro.")
        c.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, th))
        c.execute("UPDATE merchants SET last_seen=? WHERE id=?", (now, m["id"]))
    return m


def logout(token: str):
    with db() as c:
        c.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))


def update_me(mid: int, name: Optional[str], upi_id: Optional[str]) -> dict:
    with db() as c:
        if name is not None:
            name = name.strip()
            if not 2 <= len(name) <= 60:
                raise AppError(400, "Shop name should be 2 to 60 letters")
            c.execute("UPDATE merchants SET name=? WHERE id=?", (name, mid))
        if upi_id is not None:
            upi_id = upi_id.strip()
            if upi_id and not valid_vpa(upi_id):
                raise AppError(400, "This UPI ID looks wrong")
            c.execute("UPDATE merchants SET upi_id=? WHERE id=?", (upi_id or None, mid))
        return public_merchant(c.execute("SELECT * FROM merchants WHERE id=?", (mid,)).fetchone())


# Customer payments are NOT sent to or stored on the server any more (Razorpay review).
# They stay only on the merchant's phone. The old "payments" table is left empty.
def razorpay_ready() -> bool:
    return bool(os.getenv("RAZORPAY_KEY_ID") and os.getenv("RAZORPAY_KEY_SECRET"))


def rzp_request(method: str, path: str, body: Optional[dict] = None) -> dict:
    """One small Razorpay API call. Check it against Razorpay's docs before going live."""
    auth = base64.b64encode(f"{os.environ['RAZORPAY_KEY_ID']}:{os.environ['RAZORPAY_KEY_SECRET']}".encode()).decode()
    req = urllib.request.Request(
        "https://api.razorpay.com/v1" + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": "Basic " + auth},
    )
    return _http_json(req)


def _get_merchant(c, mid):
    m = c.execute("SELECT * FROM merchants WHERE id=?", (mid,)).fetchone()
    if not m:
        raise AppError(404, "No such merchant")
    return m


def create_subscription(mid: int, plan_id: str) -> dict:
    now = now_ms()
    with db() as c:
        plan = get_plans(c).get(plan_id)
        if not plan:
            raise AppError(400, "Unknown plan")
        m = _get_merchant(c, mid)
        if not (m["name"] and m["upi_id"]):
            raise AppError(400, "Please add your shop name and UPI ID first")
        if m["plan"] == plan_id and m["autopay_status"] in ("authenticated", "active"):
            raise AppError(409, f"AutoPay for {plan['name']} is already on")
        trial = not m["trial_used"]
        use_api = razorpay_ready() and bool(plan["rzp_plan_id"])
        if not use_api and not plan["link"]:
            raise AppError(503, "AutoPay is not set up yet. Please contact Payvoro.")
        method = "autopay" if use_api else "link"
        sub_id = c.insert(
            "INSERT INTO subscriptions(merchant_id, plan, amount, method, created_at, trial) VALUES (?,?,?,?,?,?)",
            (mid, plan_id, plan["price"], method, now, int(trial)),
        )

    if method == "link":
        return {"request_id": sub_id, "method": "link", "url": plan["link"], "amount": plan["price"],
                "trial": trial, "email": m["email"] or ""}

    body = {
        "plan_id": plan["rzp_plan_id"],
        "total_count": 120,                 # up to 10 years of monthly charges
        "quantity": 1,
        "customer_notify": 1,
        "notes": {"merchant_id": str(mid), "request_id": str(sub_id), "email": m["email"] or ""},
    }
    if m["email"]:
        body["notify_info"] = {"notify_email": m["email"]}
    if trial:
        body["start_at"] = now // 1000 + TRIAL_DAYS * 86400       # first charge after the free days
    try:
        rsub = rzp_request("POST", "/subscriptions", body)
    except Exception:
        log.exception("razorpay subscription failed")
        raise AppError(502, "AutoPay page could not be opened. Try again.")
    with db() as c:
        c.execute("UPDATE subscriptions SET provider_ref=? WHERE id=?", (rsub["id"], sub_id))
    return {"request_id": sub_id, "method": "autopay", "url": rsub["short_url"], "amount": plan["price"],
            "trial": trial, "email": m["email"] or ""}


def create_manual_payment(mid: int, plan_id: str) -> dict:
    """Backup: merchant pays one month on your razorpay.me page. You approve it on the admin page."""
    with db() as c:
        plan = get_plans(c).get(plan_id)
        if not plan:
            raise AppError(400, "Unknown plan")
        sub_id = c.insert(
            "INSERT INTO subscriptions(merchant_id, plan, amount, method, created_at) VALUES (?,?,?,'manual',?)",
            (mid, plan_id, plan["price"], now_ms()),
        )
    return {"request_id": sub_id, "method": "manual", "url": RAZORPAY_ME_LINK, "amount": plan["price"]}


def activate_subscription(sub_id: int, payment_ref: Optional[str] = None) -> bool:
    """Admin approves a manual payment: adds 30 days. Safe to call twice (second call does nothing)."""
    now = now_ms()
    with db() as c:
        s = c.execute("SELECT * FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
        if not s or s["status"] != "pending":
            return False
        m = _get_merchant(c, s["merchant_id"])
        days = PLANS[s["plan"]]["days"]
        new_until = max(now, m["plan_until"]) + days * DAY_MS
        c.execute("UPDATE subscriptions SET status='paid', paid_at=?, payment_ref=? WHERE id=?", (now, payment_ref, sub_id))
        c.execute("UPDATE merchants SET plan=?, plan_until=?, on_trial=0 WHERE id=?", (s["plan"], new_until, m["id"]))
        _add_charge(c, m["id"], sub_id, int(s["amount"]), s["method"], None, now)
        log_admin(c, "approved", m["id"], f"Pay-by-link payment #{sub_id} approved: +{days} days")
    return True


def _add_charge(c, mid: int, sub_id: Optional[int], amount: int, method: str, payment_ref: Optional[str], at: int):
    """One payment from a merchant to Payvoro. The same Razorpay payment is never counted twice."""
    if payment_ref and c.execute("SELECT 1 FROM charges WHERE payment_ref=?", (payment_ref,)).fetchone():
        return
    c.execute("INSERT INTO charges(merchant_id, subscription_id, amount, method, payment_ref, paid_at) VALUES (?,?,?,?,?,?)",
              (mid, sub_id, amount, method, payment_ref, at))


def verify_razorpay_signature(body: bytes, signature: str) -> bool:
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _event_email(event: dict, rsub: dict) -> str:
    pay = event.get("payload", {}).get("payment", {}).get("entity", {}) or {}
    notes = rsub.get("notes") or {}
    if not isinstance(notes, dict):
        notes = {}
    for v in (pay.get("email"), notes.get("email"), notes.get("Email")):
        if v and "@" in str(v):
            return str(v).strip().lower()
    return ""


def _rzp_amount(c, plans: dict, rsub: dict, plan_id: str) -> int:
    """Monthly amount of this AutoPay. An old plan_id keeps its old price."""
    r = c.execute("SELECT amount FROM rzp_plans WHERE rzp_plan_id=?", (rsub.get("plan_id") or "",)).fetchone()
    return int(r["amount"]) if r else int(plans[plan_id]["price"])


def _find_request(c, event: dict, rsub: dict):
    """Which merchant + plan is this Razorpay subscription for?"""
    s = c.execute("SELECT * FROM subscriptions WHERE provider_ref=?", (rsub["id"],)).fetchone()
    if s:
        return s
    # Made from your AutoPay link (rzp.io): match the plan by plan_id and the merchant by email.
    plans = get_plans(c)
    plan_id = _plan_for_rzp_id(c, plans, rsub.get("plan_id"))
    email = _event_email(event, rsub)
    if not email:
        return None
    m = c.execute("SELECT * FROM merchants WHERE lower(email)=?", (email,)).fetchone()
    if not m:
        return None
    # Newest "link" request from this merchant tells us the plan if plan_id is not configured
    req = c.execute("SELECT * FROM subscriptions WHERE merchant_id=? AND method='link' AND provider_ref IS NULL"
                    " ORDER BY id DESC LIMIT 1", (m["id"],)).fetchone()
    if req and (plan_id is None or req["plan"] == plan_id):
        c.execute("UPDATE subscriptions SET provider_ref=? WHERE id=?", (rsub["id"], req["id"]))
    elif plan_id:
        c.execute("INSERT INTO subscriptions(merchant_id, plan, amount, method, provider_ref, created_at, trial)"
                  " VALUES (?,?,?,'link',?,?,?)",
                  (m["id"], plan_id, _rzp_amount(c, plans, rsub, plan_id), rsub["id"], now_ms(), int(not m["trial_used"])))
    else:
        return None
    return c.execute("SELECT * FROM subscriptions WHERE provider_ref=?", (rsub["id"],)).fetchone()


def _subscription_event(c, kind: str, event: dict, rsub: dict):
    """Returns an old Razorpay subscription id to cancel (after a plan switch), or None."""
    s = _find_request(c, event, rsub)
    if not s:
        return {"ignored": "unknown subscription"}, None
    m = _get_merchant(c, s["merchant_id"])
    now = now_ms()
    old = m["autopay_ref"] if m["autopay_ref"] and m["autopay_ref"] != rsub["id"] else None
    is_current = m["autopay_ref"] == rsub["id"]

    if kind in ("subscription.authenticated", "subscription.activated", "subscription.charged"):
        # This subscription becomes the merchant's AutoPay (switching plan replaces the old one)
        status = "active" if kind != "subscription.authenticated" else "authenticated"
        c.execute("UPDATE merchants SET autopay_ref=?, autopay_status=?, plan=? WHERE id=?",
                  (rsub["id"], status, s["plan"], m["id"]))
        c.execute("UPDATE subscriptions SET status=CASE WHEN status='pending' THEN 'authorised' ELSE status END"
                  " WHERE id=?", (s["id"],))
        start_at = int(rsub.get("start_at") or 0) * 1000
        if not m["trial_used"] and (s["trial"] or start_at > now + 3_600_000):
            # Free trial starts now. First charge comes after TRIAL_DAYS.
            until = max(m["plan_until"], now + TRIAL_DAYS * DAY_MS)
            c.execute("UPDATE merchants SET plan_until=?, trial_used=1, on_trial=1 WHERE id=?", (until, m["id"]))
        if kind == "subscription.charged":
            end = int(rsub.get("current_end") or 0) * 1000 or now + 30 * DAY_MS
            m = _get_merchant(c, m["id"])
            c.execute("UPDATE merchants SET plan_until=?, on_trial=0, trial_used=1 WHERE id=?",
                      (max(m["plan_until"], end), m["id"]))
            pay = event.get("payload", {}).get("payment", {}).get("entity", {}) or {}
            pay_id = pay.get("id")
            c.execute("UPDATE subscriptions SET status='paid', paid_at=?, payment_ref=COALESCE(?, payment_ref) WHERE id=?",
                      (now, pay_id, s["id"]))
            amount = int(pay["amount"]) // 100 if pay.get("amount") else int(s["amount"])     # Razorpay sends paise
            _add_charge(c, m["id"], s["id"], amount, s["method"], pay_id, now)
        return {"ok": kind}, old

    if not is_current:
        return {"ignored": "old subscription"}, None
    if kind in ("subscription.pending", "subscription.halted"):
        # Charge failed. Voice keeps working for GRACE_DAYS after plan_until, then stops.
        c.execute("UPDATE merchants SET autopay_status=? WHERE id=?", (kind.split(".")[1], m["id"]))
    elif kind in ("subscription.cancelled", "subscription.completed"):
        # Paid days still work. No more charges.
        c.execute("UPDATE merchants SET autopay_status='cancelled', on_trial=0 WHERE id=?", (m["id"],))
    return {"ok": kind}, None


def cancel_autopay(rzp_sub_id: str):
    """Stops an old AutoPay after a plan switch. Link-made subscriptions can also be cancelled by API."""
    if not razorpay_ready():
        log.warning("Cancel old AutoPay %s by hand in the Razorpay dashboard (no API keys)", rzp_sub_id)
        return
    try:
        rzp_request("POST", f"/subscriptions/{rzp_sub_id}/cancel", {"cancel_at_cycle_end": 0})
    except Exception:
        log.exception("could not cancel %s - cancel it in the Razorpay dashboard", rzp_sub_id)


def handle_razorpay_webhook(body: bytes, signature: str, event_id: Optional[str] = None) -> dict:
    if not verify_razorpay_signature(body, signature):
        raise AppError(400, "Bad signature")
    event = json.loads(body.decode())
    kind = event.get("event", "")
    to_cancel = None
    with db() as c:
        if event_id:
            if c.execute("SELECT 1 FROM events WHERE id=?", (event_id,)).fetchone():
                return {"duplicate": True}
            c.execute("INSERT INTO events(id, created_at) VALUES (?,?)", (event_id, now_ms()))
        if kind.startswith("subscription."):
            rsub = event.get("payload", {}).get("subscription", {}).get("entity", {})
            if not rsub.get("id"):
                return {"ignored": kind}
            result, to_cancel = _subscription_event(c, kind, event, rsub)
        else:
            result = {"ignored": kind}
    if to_cancel:
        cancel_autopay(to_cancel)
    return result


# ---------------- admin ----------------
IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30))     # India time (servers like Vercel run in UTC)


def _start_of_day_ms() -> int:
    t = _dt.datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(t.timestamp() * 1000)


def _start_of_month_ms() -> int:
    t = _dt.datetime.now(IST).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(t.timestamp() * 1000)


def merchant_status(d: dict, now: int) -> str:
    """One word for the admin page: basic / trial / expired / no_plan / stopped"""
    if not d["active"]:
        return "stopped"
    if d["plan_until"] > now:
        return "trial" if d["on_trial"] else (d["plan"] if d["plan"] in PLANS else "basic")
    return "expired" if d["plan_until"] else "no_plan"


def admin_list_merchants() -> list:
    # Customer payments are NOT stored on the server (Razorpay review), so no sales totals here.
    now = now_ms()
    with db() as c:
        rows = c.execute(
            """
            SELECT m.* FROM merchants m ORDER BY m.id DESC
            """
        ).fetchall()
        amounts = {r["provider_ref"]: int(r["amount"]) for r in c.execute(
            "SELECT s.provider_ref, s.amount FROM subscriptions s JOIN merchants m ON m.autopay_ref = s.provider_ref"
        ).fetchall()}
        paid = {r["merchant_id"]: (int(r["total"] or 0), int(r["n"])) for r in c.execute(
            "SELECT merchant_id, SUM(amount) AS total, COUNT(*) AS n FROM charges GROUP BY merchant_id").fetchall()}
        devices = {r["merchant_id"]: int(r["n"]) for r in c.execute(
            "SELECT merchant_id, COUNT(*) AS n FROM sessions GROUP BY merchant_id").fetchall()}
        plans = get_plans(c)
    out = []
    for r in rows:
        d = dict(r)
        d["plan_active"] = bool(d["active"]) and d["plan_until"] > now
        d["online"] = bool(d["last_seen"]) and now - d["last_seen"] < 30 * 60_000
        d["status"] = merchant_status(d, now)
        d["autopay_on"] = d["autopay_status"] in ("authenticated", "active")
        # Monthly AutoPay amount: what their Razorpay plan charges (old price stays for old subscribers)
        d["autopay_amount"] = amounts.get(d["autopay_ref"]) or (plans[d["plan"]]["price"] if d["plan"] in plans else 0)
        # Plan ends within 3 days and AutoPay will NOT renew it → call / remind this merchant
        d["ending_soon"] = d["plan_active"] and d["plan_until"] - now < 3 * DAY_MS and not d["autopay_on"]
        d["shop_ready"] = bool(d["name"] and d["upi_id"])
        d["paid_total"], d["paid_count"] = paid.get(d["id"], (0, 0))
        d["devices"] = devices.get(d["id"], 0)
        d.pop("google_sub", None)
        out.append(d)
    return out


def admin_stats(merchants: Optional[list] = None) -> dict:
    """Numbers for the top of the admin dashboard."""
    ms = merchants if merchants is not None else admin_list_merchants()
    now = now_ms()
    by = {k: 0 for k in ("basic", "trial", "expired", "no_plan", "stopped")}
    for m in ms:
        by[m["status"]] = by.get(m["status"], 0) + 1
    paying = [m for m in ms if m["status"] == "basic"]
    plans = get_plans()
    plan_rows = []
    for k, p in plans.items():
        plan_rows.append({
            "id": k, "name": p["name"], "price": p["price"], "per_day": p["per_day"],
            "rzp_plan_id": p["rzp_plan_id"], "link": p["link"],
            "paying": sum(1 for m in ms if m["status"] == k),
            "trial": sum(1 for m in ms if m["status"] == "trial" and m["plan"] == k),
            "autopay_on": sum(1 for m in ms if m["autopay_on"] and m["plan"] == k),
        })
    return {
        "total_users": len(ms),
        "by_status": by,
        "paying": len(paying),
        "autopay_on": sum(1 for m in ms if m["autopay_on"]),
        "autopay_failed": sum(1 for m in ms if m["autopay_status"] in ("pending", "halted")),
        "online": sum(1 for m in ms if m["online"]),
        "new_7_days": sum(1 for m in ms if m["created_at"] > now - 7 * DAY_MS),
        "monthly_income": sum(m["autopay_amount"] for m in paying),
        "ending_soon": sum(1 for m in ms if m["ending_soon"]),
        "active_today": sum(1 for m in ms if m["last_seen"] and now - m["last_seen"] < DAY_MS),
        "not_set_up": sum(1 for m in ms if not m["shop_ready"]),
        "plans": plan_rows,
        "setup": setup_status(),
    }


def setup_status() -> dict:
    key = os.getenv("RAZORPAY_KEY_ID", "")
    return {
        "database": "postgres" if database.is_postgres() else "sqlite",
        "database_ok": database.is_postgres() or not database.on_vercel(),
        "razorpay_keys": razorpay_ready(),
        "razorpay_mode": "live" if key.startswith("rzp_live") else ("test" if key else ""),
        "webhook_secret": bool(os.getenv("RAZORPAY_WEBHOOK_SECRET")),
        "cron_secret": bool(os.getenv("CRON_SECRET")),
        "google_login": bool(GOOGLE_CLIENT_ID),
        "dev_mode": DEV,
        "allow_signup": ALLOW_SIGNUP,
        "trial_days": TRIAL_DAYS,
        # Contact details for /terms, /privacy, /refund (Razorpay checks these pages)
        "legal_missing": legal_pages.missing_details(),
    }


def admin_create_merchant(name: str, email: str, phone: Optional[str], upi_id: Optional[str], city: Optional[str],
                          plan: str, months: int) -> dict:
    """Add a merchant before they log in. They then log in with this Google email."""
    email = (email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise AppError(400, "Enter the merchant's Google email")
    phone = normalize_phone(phone) if phone else None
    if plan not in ("none", "basic"):
        raise AppError(400, "Unknown plan")
    if upi_id and not valid_vpa(upi_id):
        raise AppError(400, "This UPI ID looks wrong")
    until = 0 if plan == "none" else now_ms() + 30 * months * DAY_MS
    with db() as c:
        if c.execute("SELECT 1 FROM merchants WHERE lower(email)=?", (email,)).fetchone():
            raise AppError(409, "This email is already added")
        if phone and c.execute("SELECT 1 FROM merchants WHERE phone=?", (phone,)).fetchone():
            raise AppError(409, "This phone is already added")
        mid = c.insert(
            "INSERT INTO merchants(name, email, phone, upi_id, city, plan, plan_until, created_at) VALUES (?,?,?,?,?,?,?,?)",
            ((name or "").strip(), email, phone, upi_id or None, city, plan, until, now_ms()),
        )
        log_admin(c, "added", mid, f"Merchant added: {email}" + (f" with {months} month(s) Basic" if plan == "basic" else ""))
    return {"id": mid, "email": email, "plan_until": until}


def admin_update_merchant(mid: int, active: Optional[bool], extend_months: Optional[int], plan: Optional[str]):
    with db() as c:
        m = c.execute("SELECT * FROM merchants WHERE id=?", (mid,)).fetchone()
        if not m:
            raise AppError(404, "No such merchant")
        if active is not None and bool(active) != bool(m["active"]):
            c.execute("UPDATE merchants SET active=? WHERE id=?", (int(active), mid))
            if not active:
                c.execute("DELETE FROM sessions WHERE merchant_id=?", (mid,))
            log_admin(c, "started" if active else "stopped", mid,
                      "Merchant started" if active else "Merchant stopped – all phones logged out")
        if plan:
            if plan not in PLANS:
                raise AppError(400, "Unknown plan")
            c.execute("UPDATE merchants SET plan=? WHERE id=?", (plan, mid))
        if extend_months:
            base = max(m["plan_until"], now_ms())
            c.execute("UPDATE merchants SET plan_until=?, on_trial=0, plan=CASE WHEN plan='none' THEN 'basic' ELSE plan END"
                      " WHERE id=?", (base + extend_months * 30 * DAY_MS, mid))


def admin_list_subscriptions(status: Optional[str] = None, method: Optional[str] = None,
                             merchant_id: Optional[int] = None, limit: int = 300) -> list:
    where, args = [], []
    if status:
        where.append("s.status=?"); args.append(status)
    if method:
        where.append("s.method=?"); args.append(method)
    if merchant_id:
        where.append("s.merchant_id=?"); args.append(int(merchant_id))
    q = ("SELECT s.*, m.name, m.phone, m.email FROM subscriptions s JOIN merchants m ON m.id = s.merchant_id"
         + (" WHERE " + " AND ".join(where) if where else "") + f" ORDER BY s.id DESC LIMIT {max(1, min(int(limit), 1000))}")
    with db() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def admin_reject_subscription(sub_id: int):
    with db() as c:
        s = c.execute("SELECT merchant_id, status FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
        c.execute("UPDATE subscriptions SET status='rejected' WHERE id=? AND status='pending'", (sub_id,))
        if s and s["status"] == "pending":
            log_admin(c, "rejected", s["merchant_id"], f"Pay-by-link payment #{sub_id} rejected")


# ---------------- admin: advanced (v4.1) ----------------
def log_admin(c, action: str, merchant_id: Optional[int], detail: str = ""):
    """Every change made from the admin page is written here (who changed what is shown on the page)."""
    c.execute("INSERT INTO admin_log(created_at, merchant_id, action, detail) VALUES (?,?,?,?)",
              (now_ms(), merchant_id, action, (detail or "")[:500]))


def admin_recent_log(limit: int = 40, merchant_id: Optional[int] = None) -> list:
    q = ("SELECT l.*, m.name, m.email FROM admin_log l LEFT JOIN merchants m ON m.id = l.merchant_id"
         + (" WHERE l.merchant_id=?" if merchant_id else "") + f" ORDER BY l.id DESC LIMIT {max(1, min(int(limit), 500))}")
    with db() as c:
        return [dict(r) for r in c.execute(q, (int(merchant_id),) if merchant_id else ()).fetchall()]


EDITABLE = ("name", "email", "phone", "upi_id", "city", "notes", "message")


def admin_edit_merchant(mid: int, fields: dict) -> dict:
    """Edit shop details, private notes and the message shown to this merchant in the app."""
    fields = {k: v for k, v in (fields or {}).items() if k in EDITABLE and v is not None}
    clean = {}
    for k, v in fields.items():
        v = str(v).strip()
        if k == "name" and v and not 2 <= len(v) <= 60:
            raise AppError(400, "Shop name should be 2 to 60 letters")
        if k == "email":
            v = v.lower()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
                raise AppError(400, "Enter a valid email")
        if k == "phone" and v:
            v = normalize_phone(v)
        if k == "upi_id" and v and not valid_vpa(v):
            raise AppError(400, "This UPI ID looks wrong")
        if k == "city":
            v = v[:60]
        if k in ("notes", "message"):
            v = v[:1000]
        clean[k] = v or None if k != "name" else v
    with db() as c:
        m = _get_merchant(c, mid)
        if "email" in clean and clean["email"] != (m["email"] or "") and \
                c.execute("SELECT 1 FROM merchants WHERE lower(email)=? AND id<>?", (clean["email"], mid)).fetchone():
            raise AppError(409, "Another merchant has this email")
        if clean.get("phone") and c.execute("SELECT 1 FROM merchants WHERE phone=? AND id<>?", (clean["phone"], mid)).fetchone():
            raise AppError(409, "Another merchant has this phone")
        changed = [k for k, v in clean.items() if (m[k] or None) != (v or None)]
        for k in changed:
            c.execute(f"UPDATE merchants SET {k}=? WHERE id=?", (clean[k], mid))
        if changed:
            shown = [("private notes" if k == "notes" else "app message" if k == "message" else k) for k in changed]
            log_admin(c, "edited", mid, "Changed " + ", ".join(shown))
    return admin_merchant_detail(mid)


def admin_give_days(mid: int, days: int, reason: str) -> dict:
    """Free days (goodwill, a payment you received outside Razorpay…). A reason is required and logged."""
    days = int(days)
    reason = (reason or "").strip()
    if not 1 <= days <= 90:
        raise AppError(400, "Days must be 1 to 90")
    if len(reason) < 3:
        raise AppError(400, "Write a short reason")
    with db() as c:
        m = _get_merchant(c, mid)
        until = max(m["plan_until"], now_ms()) + days * DAY_MS
        c.execute("UPDATE merchants SET plan_until=?, plan=CASE WHEN plan IN ('none','trial','plus') THEN 'basic' ELSE plan END"
                  " WHERE id=?", (until, mid))
        log_admin(c, "free_days", mid, f"+{days} free days – {reason[:200]}")
    return admin_merchant_detail(mid)


def admin_end_plan(mid: int, reason: str) -> dict:
    """Ends the plan now. Voice stops at the app's next refresh (no grace days). AutoPay in Razorpay is NOT cancelled."""
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise AppError(400, "Write a short reason")
    with db() as c:
        m = _get_merchant(c, mid)
        if m["plan_until"] == 0:
            raise AppError(400, "This merchant has no plan")
        until = min(m["plan_until"], now_ms() - GRACE_DAYS * DAY_MS - 1)
        c.execute("UPDATE merchants SET plan_until=?, on_trial=0 WHERE id=?", (max(until, 1), mid))
        log_admin(c, "plan_ended", mid, f"Plan ended – {reason[:200]}")
    return admin_merchant_detail(mid)


def admin_logout_devices(mid: int) -> int:
    with db() as c:
        _get_merchant(c, mid)
        n = len(c.execute("SELECT token_hash FROM sessions WHERE merchant_id=?", (mid,)).fetchall())
        c.execute("DELETE FROM sessions WHERE merchant_id=?", (mid,))
        log_admin(c, "logged_out", mid, f"Logged out {n} device(s)")
    return n


def admin_delete_merchant(mid: int):
    """Only for test / duplicate accounts. A merchant who ever paid can't be deleted (keep the record – stop instead)."""
    with db() as c:
        m = _get_merchant(c, mid)
        if c.execute("SELECT 1 FROM charges WHERE merchant_id=?", (mid,)).fetchone():
            raise AppError(409, "This merchant has paid before. Stop the account instead of deleting it.")
        c.execute("DELETE FROM sessions WHERE merchant_id=?", (mid,))
        c.execute("DELETE FROM subscriptions WHERE merchant_id=?", (mid,))
        c.execute("DELETE FROM payments WHERE merchant_id=?", (mid,))
        c.execute("DELETE FROM merchants WHERE id=?", (mid,))
        log_admin(c, "deleted", None, f"Deleted merchant #{mid} {m['name'] or ''} <{m['email'] or ''}>")


def admin_bulk(ids: list, action: str) -> int:
    ids = sorted({int(i) for i in ids or []})
    if not ids:
        raise AppError(400, "Select at least one merchant")
    if action not in ("stop", "start", "logout", "autopay_check"):
        raise AppError(400, "Unknown action")
    if action == "autopay_check":
        import autopay_sync
        if len(ids) > 30:
            raise AppError(400, "Check up to 30 merchants at a time (or use \"Check AutoPay now\" for all)")
        for mid in ids:
            autopay_sync.sync(merchant_id=mid, days=60)
        return len(ids)
    for mid in ids:
        if action == "logout":
            admin_logout_devices(mid)
        else:
            admin_update_merchant(mid, action == "start", None, None)
    return len(ids)


def admin_merchant_detail(mid: int) -> dict:
    """Everything the "Manage" window shows for one merchant."""
    m = next((x for x in admin_list_merchants() if x["id"] == int(mid)), None)
    if m is None:
        raise AppError(404, "No such merchant")
    with db() as c:
        devices = [dict(r) for r in c.execute(
            "SELECT device, created_at, last_seen FROM sessions WHERE merchant_id=? ORDER BY COALESCE(last_seen, created_at) DESC",
            (int(mid),)).fetchall()]
        charges = [dict(r) for r in c.execute(
            "SELECT id, amount, method, payment_ref, paid_at FROM charges WHERE merchant_id=? ORDER BY paid_at DESC LIMIT 100",
            (int(mid),)).fetchall()]
    return {
        "merchant": m, "devices": devices, "charges": charges,
        "subscriptions": admin_list_subscriptions(merchant_id=mid, limit=100),
        "log": admin_recent_log(50, mid),
    }


# ---------- notice to all merchants (shown on the app's Home screen) ----------
def get_setting(key: str, default: str = "") -> str:
    with db() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return (r["value"] if r else None) or default


def set_setting(key: str, value: str):
    with db() as c:
        c.execute("DELETE FROM settings WHERE key=?", (key,))
        c.execute("INSERT INTO settings(key, value, updated_at) VALUES (?,?,?)", (key, value, now_ms()))


def get_notice() -> str:
    return get_setting("notice")


def admin_set_notice(text: str) -> str:
    text = (text or "").strip()[:500]
    set_setting("notice", text)
    with db() as c:
        log_admin(c, "notice", None, ("App notice: " + text) if text else "App notice removed")
    return text


def app_notice_for(m) -> str:
    """Text for the app's Home screen: the message for this merchant first, then the notice for everyone."""
    keys = m.keys() if hasattr(m, "keys") else []
    own = (m["message"] if "message" in keys else None) or ""
    return "\n\n".join(t for t in (own.strip(), get_notice()) if t)


# ---------- charts ----------
def admin_charts() -> dict:
    """New users per day (last 30 days) and money received per month (last 6 months), India time."""
    today = _dt.datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    days = [today - _dt.timedelta(days=i) for i in range(29, -1, -1)]
    first = int(days[0].timestamp() * 1000)
    months = []
    y, mo = today.year, today.month
    for _ in range(6):
        months.insert(0, _dt.datetime(y, mo, 1, tzinfo=IST))
        y, mo = (y, mo - 1) if mo > 1 else (y - 1, 12)
    m_first = int(months[0].timestamp() * 1000)
    with db() as c:
        joined = [r["created_at"] for r in c.execute("SELECT created_at FROM merchants WHERE created_at>=?", (first,)).fetchall()]
        paid = [(r["paid_at"], int(r["amount"])) for r in c.execute(
            "SELECT paid_at, amount FROM charges WHERE paid_at>=?", (m_first,)).fetchall()]

    def day_key(ms):
        return _dt.datetime.fromtimestamp(ms / 1000, IST).strftime("%Y-%m-%d")

    def month_key(ms):
        return _dt.datetime.fromtimestamp(ms / 1000, IST).strftime("%Y-%m")

    per_day = {d.strftime("%Y-%m-%d"): 0 for d in days}
    for t in joined:
        k = day_key(t)
        if k in per_day:
            per_day[k] += 1
    per_month = {mm.strftime("%Y-%m"): 0 for mm in months}
    for t, a in paid:
        k = month_key(t)
        if k in per_month:
            per_month[k] += a
    return {
        "signups": [{"label": d.strftime("%d %b"), "value": per_day[d.strftime("%Y-%m-%d")]} for d in days],
        "income": [{"label": mm.strftime("%b %Y"), "value": per_month[mm.strftime("%Y-%m")]} for mm in months],
    }
