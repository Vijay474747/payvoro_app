"""
AutoPay check straight from Razorpay ("sync").

The Razorpay webhook is the fast way to learn that a merchant set UPI AutoPay. But if the webhook is not set up,
fails, or the merchant typed a different email on the Razorpay page, Payvoro never heard about it, and the
admin page showed "—". This module asks Razorpay itself (needs RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET):

  1. Every AutoPay Payvoro already knows (subscriptions.provider_ref) is fetched and its status applied:
     authenticated / active / pending / halted / cancelled, the paid-until date and every monthly charge.
  2. New AutoPays made from your AutoPay link (rzp.io) are found in Razorpay's list and matched to a shop by
     email, then mobile number, then UPI ID (from the subscription notes, the Razorpay customer and the payment).
  3. AutoPays that match no shop are kept in "rzp_unmatched". The admin links them to the right shop once.

It runs by itself:
  - when the merchant opens the app after starting AutoPay (GET /api/me, at most every 5 minutes per merchant),
  - once a day by Vercel Cron (GET /api/cron/autopay-sync, see vercel.json),
  - from the admin page: "Check AutoPay now" (all) or "Check with Razorpay" (one merchant).

The same rules as the webhook are used (core._subscription_event), so both ways give the same result.
"""
import json
import logging
import time
import urllib.parse
from typing import Optional

import core
from core import AppError, DAY_MS, now_ms

log = logging.getLogger("payvoro")

AUTO_CHECK_EVERY_MS = 5 * 60_000          # /api/me: ask Razorpay at most this often per merchant
TIME_BUDGET_S = 25                        # stop a big sync before the server's time limit; run again to continue
LIVE = ("authenticated", "active", "pending", "halted")
STATUS_EVENT = {
    "authenticated": "subscription.authenticated",
    "active": "subscription.activated",
    "pending": "subscription.pending",
    "halted": "subscription.halted",
    "cancelled": "subscription.cancelled",
    "completed": "subscription.completed",
    "expired": "subscription.cancelled",
}


# ---------------- database ----------------
UNMATCHED_SCHEMA = """
CREATE TABLE IF NOT EXISTS rzp_unmatched(
    rzp_sub_id TEXT PRIMARY KEY,
    status TEXT,
    plan_id TEXT,
    email TEXT,
    phone TEXT,
    vpa TEXT,
    amount INTEGER NOT NULL DEFAULT 0,
    short_url TEXT,
    created_at INTEGER NOT NULL,
    seen_at INTEGER NOT NULL,
    ignored INTEGER NOT NULL DEFAULT 0
);
"""


def init_db():
    """Called from core.init_db(): the unmatched table + merchants.autopay_checked_at."""
    with core.db() as c:
        if c.pg:
            c.execute("SELECT pg_advisory_xact_lock(724002)")      # two Vercel instances starting at once
            c.executescript(core.database.to_postgres_schema(UNMATCHED_SCHEMA))
            c.execute("ALTER TABLE merchants ADD COLUMN IF NOT EXISTS autopay_checked_at BIGINT")
            return
        c.executescript(UNMATCHED_SCHEMA)
        cols = {r["name"] for r in c.execute("PRAGMA table_info(merchants)")}
        if "autopay_checked_at" not in cols:
            c.execute("ALTER TABLE merchants ADD COLUMN autopay_checked_at INTEGER")


# ---------------- Razorpay calls ----------------
def _get(path: str, params: Optional[dict] = None) -> dict:
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    return core.rzp_request("GET", path + q)


def _list_subscriptions(since_ms: int, plan_id: str, deadline: float) -> list:
    """Razorpay subscriptions created since [since_ms], newest first (100 per page)."""
    out, skip = [], 0
    while time.time() < deadline and skip < 2000:
        params = {"from": since_ms // 1000, "count": 100, "skip": skip}
        if plan_id:
            params["plan_id"] = plan_id
        items = (_get("/subscriptions", params) or {}).get("items") or []
        out.extend(items)
        if len(items) < 100:
            break
        skip += 100
    return out


def _paid_invoices(rsub_id: str) -> list:
    """Paid monthly charges of one subscription, oldest first."""
    items = (_get("/invoices", {"subscription_id": rsub_id, "count": 100}) or {}).get("items") or []
    paid = [i for i in items if i.get("status") == "paid" and i.get("payment_id")]
    return sorted(paid, key=lambda i: int(i.get("paid_at") or i.get("created_at") or 0))


def _contact(rsub: dict) -> dict:
    """Email / mobile / UPI ID the merchant used on the Razorpay page (notes → customer → first payment)."""
    found = {"email": "", "phone": "", "vpa": ""}

    def take(email=None, phone=None, vpa=None):
        if email and "@" in str(email) and not found["email"]:
            found["email"] = str(email).strip().lower()
        if phone and not found["phone"]:
            try:
                found["phone"] = core.normalize_phone(str(phone))
            except AppError:
                pass
        if vpa and core.valid_vpa(str(vpa)) and not found["vpa"]:
            found["vpa"] = str(vpa).strip().lower()

    notes = rsub.get("notes") if isinstance(rsub.get("notes"), dict) else {}
    for k, v in (notes or {}).items():
        k = str(k).lower()
        if "mail" in k:
            take(email=v)
        elif "phone" in k or "mobile" in k or "contact" in k:
            take(phone=v)
        elif "upi" in k or "vpa" in k:
            take(vpa=v)
    if rsub.get("customer_id"):
        try:
            cu = _get(f"/customers/{rsub['customer_id']}")
            take(cu.get("email"), cu.get("contact"))
        except Exception:
            log.warning("could not read Razorpay customer %s", rsub.get("customer_id"))
    if not (found["email"] and found["vpa"]):
        try:
            for inv in (_get("/invoices", {"subscription_id": rsub["id"], "count": 5}) or {}).get("items") or []:
                if inv.get("payment_id"):
                    pay = _get(f"/payments/{inv['payment_id']}")
                    take(pay.get("email"), pay.get("contact"), pay.get("vpa") or (pay.get("upi") or {}).get("vpa"))
                    break
        except Exception:
            log.warning("could not read payments of %s", rsub.get("id"))
    return found


# ---------------- matching ----------------
def _match_merchant(c, info: dict):
    if info.get("email"):
        m = c.execute("SELECT * FROM merchants WHERE lower(email)=?", (info["email"],)).fetchone()
        if m:
            return m, "email"
    if info.get("phone"):
        m = c.execute("SELECT * FROM merchants WHERE phone=?", (info["phone"],)).fetchone()
        if m:
            return m, "mobile number"
    if info.get("vpa"):
        rows = c.execute("SELECT * FROM merchants WHERE lower(upi_id)=?", (info["vpa"],)).fetchall()
        if len(rows) == 1:                       # a shared UPI ID could be two shops – then the admin decides
            return rows[0], "UPI ID"
    return None, ""


def _plan_of(c, rsub: dict) -> str:
    plans = core.get_plans(c)
    return core._plan_for_rzp_id(c, plans, rsub.get("plan_id")) or "basic"


def _attach(c, m, rsub: dict) -> dict:
    """Make sure a subscriptions row exists for this Razorpay subscription, for merchant [m]."""
    s = c.execute("SELECT * FROM subscriptions WHERE provider_ref=?", (rsub["id"],)).fetchone()
    if s:
        return s
    plan = _plan_of(c, rsub)
    req = c.execute("SELECT * FROM subscriptions WHERE merchant_id=? AND method='link' AND provider_ref IS NULL"
                    " ORDER BY id DESC LIMIT 1", (m["id"],)).fetchone()
    if req:
        c.execute("UPDATE subscriptions SET provider_ref=? WHERE id=?", (rsub["id"], req["id"]))
    else:
        plans = core.get_plans(c)
        c.insert("INSERT INTO subscriptions(merchant_id, plan, amount, method, provider_ref, created_at, trial)"
                 " VALUES (?,?,?,'link',?,?,?)",
                 (m["id"], plan, core._rzp_amount(c, plans, rsub, plan), rsub["id"],
                  int(rsub.get("created_at") or 0) * 1000 or now_ms(), int(not m["trial_used"])))
    c.execute("DELETE FROM rzp_unmatched WHERE rzp_sub_id=?", (rsub["id"],))
    return c.execute("SELECT * FROM subscriptions WHERE provider_ref=?", (rsub["id"],)).fetchone()


def _is_older_than_current(c, m, s) -> bool:
    """Never let an OLD AutoPay take over from a newer one that is working (would cancel the newer one)."""
    ref = m["autopay_ref"]
    if not ref or ref == s["provider_ref"] or m["autopay_status"] not in ("authenticated", "active", "pending"):
        return False
    cur = c.execute("SELECT id FROM subscriptions WHERE provider_ref=?", (ref,)).fetchone()
    return bool(cur) and cur["id"] > s["id"]


def _snapshot(m) -> tuple:
    return (m["autopay_ref"], m["autopay_status"], int(m["plan_until"] or 0), m["plan"])


def _apply(c, s, rsub: dict, report: dict) -> Optional[str]:
    """Applies Razorpay's current state. Returns an old AutoPay id to cancel, or None."""
    status = rsub.get("status") or ""
    kind = STATUS_EVENT.get(status)
    m = core._get_merchant(c, s["merchant_id"])
    if not kind:                                   # "created": merchant opened the page but did not finish
        return None
    if status in ("authenticated", "active") and _is_older_than_current(c, m, s):
        report["skipped_old"] += 1
        return None
    before = _snapshot(m)
    to_cancel = None
    if status not in ("authenticated", "active") and not m["autopay_ref"]:
        # First time Payvoro hears of it and it is already failing / stopped: it is still this merchant's AutoPay,
        # so the admin page shows "halted" / "cancelled" instead of "—".
        c.execute("UPDATE merchants SET autopay_ref=?, plan=CASE WHEN plan IN ('none','trial','plus') THEN ? ELSE plan END"
                  " WHERE id=?", (rsub["id"], s["plan"], m["id"]))
    _, old = core._subscription_event(c, kind, {"payload": {}}, rsub)
    to_cancel = old or to_cancel
    if status in ("active", "pending", "halted", "cancelled", "completed"):
        # Monthly charges Razorpay already took. paid_count = how many cycles were charged.
        n = int(rsub.get("paid_count") or 0)
        if n:
            have = {r["payment_ref"] for r in c.execute(
                "SELECT payment_ref FROM charges WHERE subscription_id=? AND payment_ref IS NOT NULL", (s["id"],)).fetchall()}
            if len(have) < n:
                now_m = core._get_merchant(c, m["id"])
                current = now_m["autopay_ref"] == rsub["id"]
                saved_status = now_m["autopay_status"]
                for inv in _paid_invoices(rsub["id"])[-n:]:
                    if inv["payment_id"] in have:
                        continue
                    paise = inv.get("amount_paid") or inv.get("amount")
                    paid_at = int(inv.get("paid_at") or 0) * 1000 or now_ms()
                    if current:
                        # Same as the webhook: extends the plan to the end of the paid month, counts the money
                        pay = {"id": inv["payment_id"], "amount": paise}
                        _, old = core._subscription_event(c, "subscription.charged", {"payload": {"payment": {"entity": pay}}}, rsub)
                        to_cancel = old or to_cancel
                        c.execute("UPDATE charges SET paid_at=? WHERE payment_ref=?", (paid_at, inv["payment_id"]))
                    else:
                        # An old AutoPay: only count the money it took, never make it the merchant's AutoPay again
                        amount = int(paise) // 100 if paise else int(s["amount"])
                        core._add_charge(c, m["id"], s["id"], amount, s["method"], inv["payment_id"], paid_at)
                    report["charges_added"] += 1
                if current and status != "active":           # a charge long ago must not hide today's failure
                    c.execute("UPDATE merchants SET autopay_status=? WHERE id=?", (saved_status, m["id"]))
    after_m = core._get_merchant(c, m["id"])
    if _snapshot(after_m) != before:
        report["updated"] += 1
        core.log_admin(c, "autopay_verified", m["id"],
                       f"AutoPay checked with Razorpay: {after_m['autopay_status'] or status} ({rsub['id']})")
    c.execute("UPDATE merchants SET autopay_checked_at=? WHERE id=?", (now_ms(), m["id"]))
    return to_cancel


def _remember_unmatched(c, rsub: dict, info: dict):
    now = now_ms()
    amount = 0
    try:
        amount = core._rzp_amount(c, core.get_plans(c), rsub, _plan_of(c, rsub))
    except Exception:
        pass
    row = c.execute("SELECT ignored FROM rzp_unmatched WHERE rzp_sub_id=?", (rsub["id"],)).fetchone()
    if row:
        c.execute("UPDATE rzp_unmatched SET status=?, email=COALESCE(NULLIF(?, ''), email), phone=COALESCE(NULLIF(?, ''), phone),"
                  " vpa=COALESCE(NULLIF(?, ''), vpa), seen_at=? WHERE rzp_sub_id=?",
                  (rsub.get("status"), info["email"], info["phone"], info["vpa"], now, rsub["id"]))
    else:
        c.execute("INSERT INTO rzp_unmatched(rzp_sub_id, status, plan_id, email, phone, vpa, amount, short_url, created_at, seen_at)"
                  " VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (rsub["id"], rsub.get("status"), rsub.get("plan_id"), info["email"], info["phone"], info["vpa"], amount,
                   rsub.get("short_url"), int(rsub.get("created_at") or 0) * 1000 or now, now))


# ---------------- the sync ----------------
def sync(merchant_id: Optional[int] = None, days: int = 45, source: str = "admin") -> dict:
    """Checks AutoPays with Razorpay. merchant_id = only that shop (quick). Returns a small report."""
    if not core.razorpay_ready():
        raise AppError(503, "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET on Vercel to check AutoPay with Razorpay")
    deadline = time.time() + TIME_BUDGET_S
    report = {"checked": 0, "matched_new": 0, "updated": 0, "charges_added": 0, "unmatched": 0,
              "skipped_old": 0, "errors": 0, "partial": False, "source": source}
    plan_id = core.PLANS["basic"].get("rzp_plan_id") or ""
    since = now_ms() - max(1, int(days)) * DAY_MS
    to_cancel = set()

    # 1. Razorpay's list of recent AutoPays (finds link-made ones Payvoro never heard about)
    try:
        listed = {r["id"]: r for r in _list_subscriptions(since, plan_id, deadline) if r.get("id")}
    except Exception:
        log.exception("Razorpay subscription list failed")
        raise AppError(502, "Could not reach Razorpay. Check the API keys and try again.")

    # 2. AutoPays Payvoro already knows that are older than the list window
    with core.db() as c:
        where, args = "", []
        if merchant_id:
            where, args = " AND merchant_id=?", [int(merchant_id)]
        known = [r["provider_ref"] for r in c.execute(
            "SELECT DISTINCT provider_ref FROM subscriptions WHERE provider_ref IS NOT NULL AND status IN ('pending','authorised','paid')"
            + where, args).fetchall()]
        known += [r["autopay_ref"] for r in c.execute(
            "SELECT autopay_ref FROM merchants WHERE autopay_ref IS NOT NULL AND autopay_ref<>''"
            + (" AND id=?" if merchant_id else ""), args).fetchall()]
        ignored = {r["rzp_sub_id"] for r in c.execute("SELECT rzp_sub_id FROM rzp_unmatched WHERE ignored=1").fetchall()}
    for ref in dict.fromkeys(known):
        if ref in listed:
            continue
        if time.time() > deadline:
            report["partial"] = True
            break
        try:
            listed[ref] = _get(f"/subscriptions/{ref}")
        except Exception:
            report["errors"] += 1
            log.warning("could not fetch %s", ref)

    # 3. Apply, oldest first (so a newer AutoPay always wins)
    for rsub in sorted(listed.values(), key=lambda r: int(r.get("created_at") or 0)):
        if time.time() > deadline:
            report["partial"] = True
            break
        if rsub["id"] in ignored:
            continue
        try:
            with core.db() as c:
                s = c.execute("SELECT * FROM subscriptions WHERE provider_ref=?", (rsub["id"],)).fetchone()
                if s is None:
                    if rsub.get("status") not in LIVE:
                        continue
                    prev = c.execute("SELECT email, phone, vpa FROM rzp_unmatched WHERE rzp_sub_id=?", (rsub["id"],)).fetchone()
                    info = {k: (prev[k] or "") for k in ("email", "phone", "vpa")} if prev else None
                    if info is None or not any(info.values()):
                        info = _contact(rsub)
                    m, how = _match_merchant(c, info)
                    if m is None:
                        _remember_unmatched(c, rsub, info)
                        report["unmatched"] += 1
                        continue
                    if merchant_id and m["id"] != int(merchant_id):
                        continue
                    s = _attach(c, m, rsub)
                    report["matched_new"] += 1
                    core.log_admin(c, "autopay_matched", m["id"], f"Razorpay AutoPay {rsub['id']} matched by {how}")
                elif merchant_id and s["merchant_id"] != int(merchant_id):
                    continue
                report["checked"] += 1
                old = _apply(c, s, rsub, report)
                if old:
                    to_cancel.add(old)
        except Exception:
            report["errors"] += 1
            log.exception("AutoPay sync failed for %s", rsub.get("id"))

    for ref in to_cancel:
        core.cancel_autopay(ref)
    if merchant_id is None:
        core.set_setting("autopay_sync", json.dumps({**report, "at": now_ms()}))
    return report


def last_sync() -> dict:
    try:
        return json.loads(core.get_setting("autopay_sync") or "{}")
    except ValueError:
        return {}


def maybe_autocheck(m):
    """GET /api/me: if this merchant is waiting for AutoPay (or a charge is due), ask Razorpay now.
    Never fails the app's request. Returns the (maybe updated) merchant row."""
    if not core.razorpay_ready():
        return m
    now = now_ms()
    keys = m.keys() if hasattr(m, "keys") else []
    checked = (m["autopay_checked_at"] if "autopay_checked_at" in keys else None) or 0
    if now - checked < AUTO_CHECK_EVERY_MS:
        return m
    with core.db() as c:
        waiting = c.execute("SELECT 1 FROM subscriptions WHERE merchant_id=? AND status='pending' AND method IN ('autopay','link')"
                            " AND created_at>?", (m["id"], now - 3 * DAY_MS)).fetchone()
    due = m["autopay_status"] in ("authenticated", "active") and m["plan_until"] < now + DAY_MS
    failing = m["autopay_status"] in ("pending", "halted")
    if not (waiting or due or failing):
        return m
    with core.db() as c:
        c.execute("UPDATE merchants SET autopay_checked_at=? WHERE id=?", (now, m["id"]))   # even if Razorpay is down
    try:
        sync(merchant_id=m["id"], days=4, source="app")
    except Exception:
        log.exception("auto AutoPay check failed for merchant %s", m["id"])
        return m
    with core.db() as c:
        return core._get_merchant(c, m["id"])


# ---------------- admin actions ----------------
def list_unmatched(include_ignored: bool = False) -> list:
    with core.db() as c:
        q = "SELECT * FROM rzp_unmatched" + ("" if include_ignored else " WHERE ignored=0") + " ORDER BY created_at DESC LIMIT 200"
        return [dict(r) for r in c.execute(q).fetchall()]


def link_unmatched(rzp_sub_id: str, merchant_id: int) -> dict:
    """Admin: "this Razorpay AutoPay belongs to that shop". Then its status is applied at once."""
    if not core.razorpay_ready():
        raise AppError(503, "Set the Razorpay API keys first")
    try:
        rsub = _get(f"/subscriptions/{rzp_sub_id}")
    except Exception:
        raise AppError(502, "Could not read this AutoPay from Razorpay")
    report = {"updated": 0, "charges_added": 0, "skipped_old": 0}
    with core.db() as c:
        m = core._get_merchant(c, int(merchant_id))
        other = c.execute("SELECT merchant_id FROM subscriptions WHERE provider_ref=?", (rzp_sub_id,)).fetchone()
        if other and other["merchant_id"] != m["id"]:
            raise AppError(409, "This AutoPay already belongs to another merchant")
        s = _attach(c, m, rsub)
        core.log_admin(c, "autopay_linked", m["id"], f"Razorpay AutoPay {rzp_sub_id} linked by admin")
        old = _apply(c, s, rsub, report)
    if old:
        core.cancel_autopay(old)
    return {"ok": True, **report}


def ignore_unmatched(rzp_sub_id: str) -> dict:
    with core.db() as c:
        c.execute("UPDATE rzp_unmatched SET ignored=1 WHERE rzp_sub_id=?", (rzp_sub_id,))
        core.log_admin(c, "autopay_ignored", None, f"Razorpay AutoPay {rzp_sub_id} marked 'not a Payvoro shop'")
    return {"ok": True}


def cancel_merchant_autopay(mid: int, reason: str) -> dict:
    """Admin stops future AutoPay charges for a merchant (paid days keep working)."""
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise AppError(400, "Write a short reason")
    with core.db() as c:
        m = core._get_merchant(c, mid)
        ref = m["autopay_ref"]
        if not ref or m["autopay_status"] not in ("authenticated", "active", "pending", "halted"):
            raise AppError(400, "This merchant has no running AutoPay")
    if not core.razorpay_ready():
        raise AppError(503, f"Cancel {ref} in the Razorpay dashboard (API keys are not set)")
    try:
        core.rzp_request("POST", f"/subscriptions/{ref}/cancel", {"cancel_at_cycle_end": 0})
    except Exception:
        raise AppError(502, "Razorpay did not cancel it. Try again or cancel it in the Razorpay dashboard.")
    with core.db() as c:
        c.execute("UPDATE merchants SET autopay_status='cancelled', on_trial=0 WHERE id=?", (mid,))
        core.log_admin(c, "autopay_cancelled", mid, f"AutoPay {ref} cancelled by admin – {reason[:200]}")
    return core.admin_merchant_detail(mid)
