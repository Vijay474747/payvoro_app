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
  RAZORPAY_PLAN_BASIC / RAZORPAY_PLAN_PLUS  Razorpay Subscription plan IDs (Rs 54 and Rs 105 monthly)
  RAZORPAY_WEBHOOK_SECRET  webhook secret (https://YOUR_DOMAIN/api/razorpay/webhook)
  RAZORPAY_LINK_BASIC / RAZORPAY_LINK_PLUS  your AutoPay links from the dashboard (used when API keys are not set;
                          the merchant must use the same email as their Google login)
  RAZORPAY_ME_LINK        backup "pay by link" page (razorpay.me) - you approve these on the admin page
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
        "id": "basic", "name": "Basic", "price": 54, "per_day": "1.8", "days": 30,
        "features": ["Voice alert in Tamil (தமிழ்)", "All UPI apps + bank SMS", "Scan & show your shop QR", "30 days payment history"],
        "flags": {"languages": ["ta", "en"], "say_name": False, "analytics": False, "history_days": 30},
        "rzp_plan_id": os.getenv("RAZORPAY_PLAN_BASIC", ""),
        "link": os.getenv("RAZORPAY_LINK_BASIC", "https://rzp.io/rzp/yONA0V4T"),
    },
    "plus": {
        "id": "plus", "name": "Plus", "price": 105, "per_day": "3.5", "days": 30,
        "features": ["Everything in Basic", "Says the customer's name", "Voice in Tamil, English & Hindi",
                     "Full analytics & reports", "Unlimited history + cloud backup"],
        "flags": {"languages": ["ta", "en", "hi"], "say_name": True, "analytics": True, "history_days": None},
        "rzp_plan_id": os.getenv("RAZORPAY_PLAN_PLUS", ""),
        "link": os.getenv("RAZORPAY_LINK_PLUS", "https://rzp.io/rzp/qTp7E5Ai"),
    },
}
PUBLIC_PLAN_KEYS = ("id", "name", "price", "per_day", "days", "features", "flags")


MAX_PRICE = 15000          # UPI AutoPay limit without extra approval (Rs)


def per_day_text(price: int) -> str:
    """54 -> '1.8', 105 -> '3.5', 60 -> '2'"""
    t = f"{price / 30:.1f}"
    return t[:-2] if t.endswith(".0") else t


def get_plans(c=None) -> dict:
    """Plans from the code (PLANS) + prices you changed on the admin page (plan_settings table)."""
    plans = copy.deepcopy(PLANS)
    if c is None:
        with db() as c2:
            rows = c2.execute("SELECT * FROM plan_settings").fetchall()
    else:
        rows = c.execute("SELECT * FROM plan_settings").fetchall()
    for r in rows:
        p = plans.get(r["plan_id"])
        if not p:
            continue
        p["price"] = int(r["price"])
        p["per_day"] = per_day_text(p["price"])
        if r["rzp_plan_id"] is not None:
            p["rzp_plan_id"] = r["rzp_plan_id"]
        if r["link"] is not None:
            p["link"] = r["link"]
    return plans


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
    on_trial INTEGER NOT NULL DEFAULT 0
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
"""

MERCHANT_COLS = ["id", "name", "phone", "upi_id", "city", "plan", "plan_until", "active", "created_at", "last_seen",
                 "google_sub", "email", "autopay_ref", "autopay_status", "trial_used", "on_trial"]


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
    with db() as c:
        if c.pg:
            # Two Vercel instances may start at the same moment: only one creates the tables.
            c.execute("SELECT pg_advisory_xact_lock(724001)")
            c.executescript(database.to_postgres_schema(SCHEMA))
            c.execute("CREATE INDEX IF NOT EXISTS idx_sub_ref ON subscriptions(provider_ref)")
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
        c.execute("DROP TABLE IF EXISTS otps")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sub_ref ON subscriptions(provider_ref)")


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
    if plan == "trial":                      # old 7-day trial accounts
        return PLANS["plus"]["flags"]
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
        info = gid.verify_oauth2_token(id_token, greq.Request(), GOOGLE_CLIENT_ID)
    except Exception:
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


def record_payments(mid: int, payments: list) -> int:
    """Saves new payments. A re-sent payment only updates its verification (late bank SMS)."""
    inserted = 0
    with db() as c:
        for p in payments[:500]:
            utr = (p.get("utr") or None)
            source = "bank" if p.get("source") == "bank" else "app"
            bank = 1 if p.get("bank_confirmed") else 0
            key = str(p["dedupe_key"])[:200]
            cur = c.execute(
                "INSERT INTO payments(merchant_id, amount, payer, app, status, ts, dedupe_key, received_at,"
                " utr, source, bank_confirmed) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(merchant_id, dedupe_key) DO NOTHING",
                (mid, float(p["amount"]), (p.get("payer") or "")[:60] or None, str(p.get("app", ""))[:40],
                 str(p.get("status", "SUCCESS"))[:10], int(p["timestamp"]), key, now_ms(),
                 utr[:20] if utr else None, source, bank),
            )
            if cur.rowcount:
                inserted += 1
            else:
                c.execute(
                    "UPDATE payments SET bank_confirmed = CASE WHEN bank_confirmed > ? THEN bank_confirmed ELSE ? END,"
                    " utr = COALESCE(utr, ?), source = CASE WHEN ? = 'app' THEN 'app' ELSE source END,"
                    " payer = COALESCE(payer, ?), app = CASE WHEN ? = 'app' THEN ? ELSE app END"
                    " WHERE merchant_id = ? AND dedupe_key = ?",
                    (bank, bank, utr, source, (p.get("payer") or None), source, str(p.get("app", ""))[:40], mid, key),
                )
    return inserted


# ---------------- subscriptions (UPI AutoPay) ----------------
#
# Three ways a merchant can pay, best first:
#   1. "autopay": the server makes a Razorpay Subscription for this merchant (needs API keys + plan IDs).
#                 The app opens its page, the merchant approves UPI AutoPay. Webhooks do the rest.
#   2. "link":    your ready-made AutoPay link (rzp.io). The merchant must use the same email as their
#                 Google login, so the webhook can find them.
#   3. "manual":  razorpay.me page, one month only. You approve it on the admin page.
#
# Free trial: the first plan only. The subscription starts TRIAL_DAYS later, so the first charge
# comes after the free days. The trial begins when Razorpay says AutoPay is approved ("authenticated").

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
    return True


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
            pay_id = event.get("payload", {}).get("payment", {}).get("entity", {}).get("id")
            c.execute("UPDATE subscriptions SET status='paid', paid_at=?, payment_ref=COALESCE(?, payment_ref) WHERE id=?",
                      (now, pay_id, s["id"]))
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
    """One word for the admin page: basic / plus / trial / expired / no_plan / stopped"""
    if not d["active"]:
        return "stopped"
    if d["plan_until"] > now:
        return "trial" if d["on_trial"] else (d["plan"] if d["plan"] in PLANS else "basic")
    return "expired" if d["plan_until"] else "no_plan"


def admin_list_merchants() -> list:
    day, month, now = _start_of_day_ms(), _start_of_month_ms(), now_ms()
    with db() as c:
        rows = c.execute(
            """
            SELECT m.*,
              COALESCE(SUM(CASE WHEN p.status='SUCCESS' AND p.ts >= ? THEN p.amount END), 0) AS today_total,
              COALESCE(SUM(CASE WHEN p.status='SUCCESS' AND p.ts >= ? THEN 1 END), 0) AS today_count,
              COALESCE(SUM(CASE WHEN p.status='SUCCESS' AND p.ts >= ? THEN p.amount END), 0) AS month_total
            FROM merchants m LEFT JOIN payments p ON p.merchant_id = m.id
            GROUP BY m.id ORDER BY m.id DESC
            """,
            (day, day, month),
        ).fetchall()
        amounts = {r["provider_ref"]: int(r["amount"]) for r in c.execute(
            "SELECT s.provider_ref, s.amount FROM subscriptions s JOIN merchants m ON m.autopay_ref = s.provider_ref"
        ).fetchall()}
        plans = get_plans(c)
    out = []
    for r in rows:
        d = dict(r)
        d["today_total"], d["month_total"] = float(d["today_total"]), float(d["month_total"])
        d["today_count"] = int(d["today_count"])
        d["plan_active"] = bool(d["active"]) and d["plan_until"] > now
        d["online"] = bool(d["last_seen"]) and now - d["last_seen"] < 30 * 60_000
        d["status"] = merchant_status(d, now)
        d["autopay_on"] = d["autopay_status"] in ("authenticated", "active")
        # Monthly AutoPay amount: what their Razorpay plan charges (old price stays for old subscribers)
        d["autopay_amount"] = amounts.get(d["autopay_ref"]) or (plans[d["plan"]]["price"] if d["plan"] in plans else 0)
        d.pop("google_sub", None)
        out.append(d)
    return out


def admin_stats(merchants: Optional[list] = None) -> dict:
    """Numbers for the top of the admin dashboard."""
    ms = merchants if merchants is not None else admin_list_merchants()
    now = now_ms()
    by = {k: 0 for k in ("basic", "plus", "trial", "expired", "no_plan", "stopped")}
    for m in ms:
        by[m["status"]] = by.get(m["status"], 0) + 1
    paying = [m for m in ms if m["status"] in ("basic", "plus")]
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
        "today_total": sum(m["today_total"] for m in ms),
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
        "google_login": bool(GOOGLE_CLIENT_ID),
        "dev_mode": DEV,
        "allow_signup": ALLOW_SIGNUP,
        "trial_days": TRIAL_DAYS,
    }


def admin_set_plan(plan_id: str, price: int, rzp_plan_id: Optional[str] = None, link: Optional[str] = None) -> dict:
    """
    Change the monthly AutoPay amount of a plan.
    Razorpay plans can't change their amount, so with API keys a NEW Razorpay plan is made.
    New merchants pay the new amount. Old AutoPays keep their old amount until they switch plan.
    """
    if plan_id not in PLANS:
        raise AppError(400, "Unknown plan")
    try:
        price = int(price)
    except (TypeError, ValueError):
        raise AppError(400, "Price must be a whole number of rupees")
    if not 1 <= price <= MAX_PRICE:
        raise AppError(400, f"Price must be between 1 and {MAX_PRICE} rupees")
    rzp_plan_id = (rzp_plan_id or "").strip() or None
    link = (link or "").strip() if link is not None else None
    if rzp_plan_id and not re.fullmatch(r"plan_[A-Za-z0-9]{6,40}", rzp_plan_id):
        raise AppError(400, "Razorpay plan ID looks wrong (it starts with plan_)")
    if link and not link.startswith("https://"):
        raise AppError(400, "AutoPay link must start with https://")

    with db() as c:
        cur = get_plans(c)[plan_id]
    changed = price != cur["price"]
    created = None
    if rzp_plan_id is None:
        if razorpay_ready() and (changed or not cur["rzp_plan_id"]):
            try:
                r = rzp_request("POST", "/plans", {
                    "period": "monthly", "interval": 1,
                    "item": {"name": f"Payvoro {cur['name']}", "amount": price * 100, "currency": "INR",
                             "description": f"Payvoro {cur['name']} - Rs {price} per month (Rs {per_day_text(price)}/day)"},
                    "notes": {"payvoro_plan": plan_id},
                })
                rzp_plan_id = created = r["id"]
            except Exception:
                log.exception("razorpay plan create failed")
                raise AppError(502, "Razorpay could not make the plan. Check your API keys and try again.")
        elif changed:
            rzp_plan_id = ""              # old Razorpay plan has the old amount: don't use it
        else:
            rzp_plan_id = cur["rzp_plan_id"]
    if link is None:
        link = "" if changed else cur["link"]     # old rzp.io link charges the old amount

    now = now_ms()
    with db() as c:
        c.execute(
            "INSERT INTO plan_settings(plan_id, price, rzp_plan_id, link, updated_at) VALUES (?,?,?,?,?)"
            " ON CONFLICT(plan_id) DO UPDATE SET price=excluded.price, rzp_plan_id=excluded.rzp_plan_id,"
            " link=excluded.link, updated_at=excluded.updated_at",
            (plan_id, price, rzp_plan_id, link, now),
        )
        for pid, amount in ((cur["rzp_plan_id"], cur["price"]), (rzp_plan_id, price)):
            if pid:
                c.execute("INSERT INTO rzp_plans(rzp_plan_id, plan, amount, created_at) VALUES (?,?,?,?)"
                          " ON CONFLICT(rzp_plan_id) DO NOTHING", (pid, plan_id, amount, now))
        plan = get_plans(c)[plan_id]
    warn = ""
    if not plan["rzp_plan_id"] and not plan["link"]:
        warn = "No Razorpay plan and no AutoPay link: merchants can't start AutoPay for this plan yet."
    return {"plan": {k: plan[k] for k in ("id", "name", "price", "per_day", "rzp_plan_id", "link")},
            "created_rzp_plan": created, "warning": warn}


def admin_create_merchant(name: str, email: str, phone: Optional[str], upi_id: Optional[str], city: Optional[str],
                          plan: str, months: int) -> dict:
    """Add a merchant before they log in. They then log in with this Google email."""
    email = (email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise AppError(400, "Enter the merchant's Google email")
    phone = normalize_phone(phone) if phone else None
    if plan not in ("none", "basic", "plus"):
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
    return {"id": mid, "email": email, "plan_until": until}


def admin_update_merchant(mid: int, active: Optional[bool], extend_months: Optional[int], plan: Optional[str]):
    with db() as c:
        m = c.execute("SELECT * FROM merchants WHERE id=?", (mid,)).fetchone()
        if not m:
            raise AppError(404, "No such merchant")
        if active is not None:
            c.execute("UPDATE merchants SET active=? WHERE id=?", (int(active), mid))
            if not active:
                c.execute("DELETE FROM sessions WHERE merchant_id=?", (mid,))
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
        c.execute("UPDATE subscriptions SET status='rejected' WHERE id=? AND status='pending'", (sub_id,))


def admin_merchant_payments(mid: int, limit: int = 100) -> list:
    with db() as c:
        return [dict(r) for r in c.execute(
            "SELECT amount, payer, app, status, ts, utr, source, bank_confirmed FROM payments"
            " WHERE merchant_id=? ORDER BY ts DESC LIMIT ?",
            (mid, min(limit, 1000)),
        ).fetchall()]
