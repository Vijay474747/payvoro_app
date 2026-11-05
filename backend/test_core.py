"""Run: python test_core.py   (or pytest). Needs no extra packages. Google and Razorpay are faked."""
import hashlib
import hmac
import json
import os
import sqlite3
import tempfile

os.environ["PAYVORO_DB"] = os.path.join(tempfile.mkdtemp(), "core.db")
os.environ["PAYVORO_DEV"] = "1"
os.environ["RAZORPAY_WEBHOOK_SECRET"] = "whsec"
for k in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_PLAN_BASIC"):
    os.environ.pop(k, None)

import core  # noqa: E402
from core import AppError  # noqa: E402

core.init_db()
DAY = core.DAY_MS

# ---- fake Razorpay API ----
CALLS = []
_ids = iter(range(1, 10_000))


def fake_rzp(method, path, body=None):
    CALLS.append((method, path, body))
    if path == "/subscriptions":
        n = next(_ids)                         # unique, like real Razorpay ids
        return {"id": f"sub_api{n}", "short_url": f"https://rzp.io/i/api{n}", "status": "created"}
    if path == "/plans":
        return {"id": f"plan_New{next(_ids):06d}", "item": body["item"]}
    return {}


def ref_of(mid, plan):
    with core.db() as c:
        return c.execute("SELECT provider_ref FROM subscriptions WHERE merchant_id=? AND plan=? ORDER BY id DESC",
                         (mid, plan)).fetchone()[0]


core.rzp_request = fake_rzp


def use_api(on: bool):
    """Turn the 'server makes the AutoPay' mode on or off."""
    if on:
        os.environ["RAZORPAY_KEY_ID"], os.environ["RAZORPAY_KEY_SECRET"] = "rzp_test_k", "s"
        core.PLANS["basic"]["rzp_plan_id"] = "plan_B"
    else:
        os.environ.pop("RAZORPAY_KEY_ID", None); os.environ.pop("RAZORPAY_KEY_SECRET", None)
        core.PLANS["basic"]["rzp_plan_id"] = ""


def expect_error(fn, status):
    try:
        fn()
    except AppError as e:
        assert e.status == status, (e.status, e.detail)
        return e.detail
    raise AssertionError("expected error")


def login(email):
    return core.login_google("dev:" + email, "test phone")


def new_shop(email, name="Ravi Stores", upi="ravi@okaxis"):
    out = login(email)
    mid = out["merchant"]["id"]
    core.update_me(mid, name, upi)
    return mid, out["token"]


def me(mid):
    with core.db() as c:
        return core.public_merchant(c.execute("SELECT * FROM merchants WHERE id=?", (mid,)).fetchone())


def hook(event, rsub, email=None, eid=None, payment=None):
    payload = {"subscription": {"entity": rsub}}
    if email or payment:
        payload["payment"] = {"entity": {"email": email, **(payment or {})}}
    body = json.dumps({"event": event, "payload": payload}).encode()
    sig = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
    return core.handle_razorpay_webhook(body, sig, eid)


# ---------------------------------------------------------------- tests

def test_google_login_new_merchant():
    out = login("ravi@gmail.com")
    m = out["merchant"]
    assert out["token"] and out["is_new"]
    assert m["plan"] == "none" and m["plan_until"] == 0 and m["needs_plan"] and not m["can_announce"]
    assert m["email"] == "ravi@gmail.com"
    # same Google account again -> same merchant
    assert login("ravi@gmail.com")["merchant"]["id"] == m["id"]
    tok = out["token"]
    assert core.merchant_by_token(tok)["id"] == m["id"]
    core.logout(tok)
    expect_error(lambda: core.merchant_by_token(tok), 401)


def test_profile_rules():
    mid, _ = new_shop("profile@gmail.com")
    assert me(mid)["upi_id"] == "ravi@okaxis"
    expect_error(lambda: core.update_me(mid, None, "not-a-upi"), 400)
    expect_error(lambda: core.update_me(mid, "x", None), 400)
    assert login("profile@gmail.com")["is_new"] is False


def test_plans_prices_and_features():
    p = {x["id"]: x for x in core.public_plans()}
    assert (p["basic"]["price"], p["basic"]["per_day"]) == (30, "1")
    assert list(p) == ["basic"]                                             # Plus plan removed
    assert p["basic"]["flags"]["languages"] == ["ta", "en"] and not p["basic"]["flags"]["say_name"]
    assert not p["basic"]["flags"]["analytics"] and p["basic"]["flags"]["history_days"] == 30
    # old "plus" / "trial" accounts get the Basic features
    assert core.plan_flags("plus") == core.plan_flags("trial") == core.plan_flags("basic")
    assert "rzp_plan_id" not in p["basic"] and "link" not in p["basic"]      # secrets stay on the server
    assert core.TRIAL_DAYS == 3


def test_need_shop_before_autopay():
    mid = login("noshop@gmail.com")["merchant"]["id"]
    expect_error(lambda: core.create_subscription(mid, "basic"), 400)
    mid2, _ = new_shop("gold@gmail.com")
    expect_error(lambda: core.create_subscription(mid2, "gold"), 400)


def test_autopay_link_trial_then_charge():
    """No API keys: the app opens your rzp.io link. Webhook finds the merchant by email."""
    use_api(False)
    mid, _ = new_shop("link@gmail.com")
    r = core.create_subscription(mid, "basic")
    assert r["method"] == "link" and r["url"] == "https://rzp.io/rzp/WO6mEyFr" and r["trial"]
    assert r["email"] == "link@gmail.com"
    assert me(mid)["needs_plan"]                       # nothing happens until Razorpay says so

    now_s = core.now_ms() // 1000
    rsub = {"id": "sub_link1", "plan_id": "plan_dashboard", "status": "authenticated", "start_at": now_s}
    assert hook("subscription.authenticated", rsub, email="LINK@gmail.com") == {"ok": "subscription.authenticated"}
    m = me(mid)
    assert m["plan"] == "basic" and m["on_trial"] and m["autopay"] and not m["needs_plan"] and m["can_announce"]
    assert abs(m["plan_until"] - (core.now_ms() + 3 * DAY)) < 5000

    end = now_s + 33 * 86400
    hook("subscription.charged", {**rsub, "status": "active", "current_end": end}, email="link@gmail.com")
    m = me(mid)
    assert m["plan_until"] == end * 1000 and not m["on_trial"] and m["autopay"]


def test_unknown_email_is_ignored():
    use_api(False)
    rsub = {"id": "sub_nobody", "plan_id": "plan_x", "status": "authenticated"}
    assert hook("subscription.authenticated", rsub, email="stranger@gmail.com") == {"ignored": "unknown subscription"}


def test_autopay_api_trial_and_switch_plan():
    """With API keys: the server makes the subscription, trial = start 3 days later."""
    use_api(True)
    CALLS.clear()
    mid, _ = new_shop("api@gmail.com")
    r = core.create_subscription(mid, "basic")
    assert r["method"] == "autopay" and r["url"].startswith("https://rzp.io/i/") and r["trial"]
    body = CALLS[0][2]
    assert body["plan_id"] == "plan_B" and body["notes"]["merchant_id"] == str(mid)
    assert abs(body["start_at"] - (core.now_ms() // 1000 + 3 * 86400)) < 5
    sub1 = {"id": ref_of(mid, "basic"), "plan_id": "plan_B", "start_at": body["start_at"]}
    hook("subscription.authenticated", sub1)
    assert me(mid)["on_trial"]
    expect_error(lambda: core.create_subscription(mid, "basic"), 409)      # already on

    expect_error(lambda: core.create_subscription(mid, "plus"), 400)       # Plus plan removed
    use_api(False)


def test_new_autopay_after_failed_one_cancels_old():
    """AutoPay failed (halted) -> merchant sets it again: no 2nd trial, the old mandate is cancelled."""
    use_api(True)
    mid, _ = new_shop("switch@gmail.com")
    core.create_subscription(mid, "basic")
    old = ref_of(mid, "basic")
    hook("subscription.authenticated", {"id": old})
    hook("subscription.halted", {"id": old})
    CALLS.clear()
    r2 = core.create_subscription(mid, "basic")
    assert not r2["trial"] and "start_at" not in CALLS[0][2]
    new = ref_of(mid, "basic")
    assert new != old
    hook("subscription.authenticated", {"id": new})
    assert ("POST", f"/subscriptions/{old}/cancel", {"cancel_at_cycle_end": 0}) in CALLS
    m = me(mid)
    assert m["plan"] == "basic" and m["autopay"]
    # events from the old subscription no longer change anything
    assert hook("subscription.cancelled", {"id": old}) == {"ignored": "old subscription"}
    assert me(mid)["autopay"]
    use_api(False)


def test_failed_charge_grace_and_cancel():
    use_api(False)
    mid, _ = new_shop("grace@gmail.com")
    core.create_subscription(mid, "basic")
    rsub = {"id": "sub_g1", "plan_id": "plan_dash"}
    hook("subscription.authenticated", rsub, email="grace@gmail.com")
    hook("subscription.halted", rsub)
    m = me(mid)
    assert m["autopay_status"] == "halted" and not m["autopay"] and m["can_announce"]
    # after the plan end + 3 grace days, voice stops
    with core.db() as c:
        c.execute("UPDATE merchants SET plan_until=? WHERE id=?", (core.now_ms() - 4 * DAY, mid))
    assert not me(mid)["can_announce"]
    hook("subscription.cancelled", rsub)
    assert me(mid)["autopay_status"] == "cancelled" and not me(mid)["needs_plan"]


def test_webhook_security_and_duplicates():
    expect_error(lambda: core.handle_razorpay_webhook(b'{"event":"x"}', "bad"), 400)
    use_api(False)
    mid, _ = new_shop("dup@gmail.com")
    core.create_subscription(mid, "basic")
    rsub = {"id": "sub_d1", "plan_id": "p"}
    hook("subscription.authenticated", rsub, email="dup@gmail.com", eid="evt_1")
    until = me(mid)["plan_until"]
    assert hook("subscription.charged", {**rsub, "current_end": 9_999_999_999}, eid="evt_1") == {"duplicate": True}
    assert me(mid)["plan_until"] == until


def test_manual_razorpay_me_payment():
    mid, _ = new_shop("manual@gmail.com")
    r = core.create_manual_payment(mid, "basic")
    assert r["method"] == "manual" and "razorpay.me" in r["url"] and r["amount"] == 30
    use_api(False)
    core.create_subscription(mid, "basic")                                  # an AutoPay try, not for approval
    expect_error(lambda: core.create_manual_payment(mid, "plus"), 400)      # Plus plan removed
    waiting = core.admin_list_subscriptions("pending", "manual")
    assert [s["id"] for s in waiting if s["merchant_id"] == mid] == [r["request_id"]]
    assert core.activate_subscription(r["request_id"], "manual") is True
    assert core.activate_subscription(r["request_id"], "manual") is False   # no double credit
    m = me(mid)
    assert m["plan"] == "basic" and m["plan_active"] and not m["needs_plan"]
    assert abs(m["plan_until"] - (core.now_ms() + 30 * DAY)) < 5000


def test_admin_adds_merchant_by_email():
    core.admin_create_merchant("Kumar Tea", "Kumar@Gmail.com", "9811122233", None, "Chennai", "basic", 1)
    expect_error(lambda: core.admin_create_merchant("X", "kumar@gmail.com", None, None, None, "none", 1), 409)
    expect_error(lambda: core.admin_create_merchant("X", "not-an-email", None, None, None, "none", 1), 400)
    expect_error(lambda: core.admin_create_merchant("X", "p@gmail.com", None, None, None, "plus", 1), 400)
    out = login("kumar@gmail.com")                                          # links to the added merchant
    m = out["merchant"]
    assert m["name"] == "Kumar Tea" and m["plan"] == "basic" and m["plan_active"] and not m["needs_plan"]


def test_customer_payments_not_stored_and_stop_logs_out():
    """Razorpay review: customer payments stay on the phone. The server has no code to store them."""
    assert not hasattr(core, "record_payments") and not hasattr(core, "admin_merchant_payments")
    mid, tok = new_shop("pay@gmail.com")
    row = next(r for r in core.admin_list_merchants() if r["id"] == mid)
    assert "today_total" not in row and "month_total" not in row and row["online"]
    assert "today_total" not in core.admin_stats()
    core.admin_update_merchant(mid, False, None, None)                     # stop -> logged out
    expect_error(lambda: core.merchant_by_token(tok), 401)
    expect_error(lambda: login("pay@gmail.com"), 403)


def test_old_database_upgrade():
    """Your existing server database (OTP login, phone NOT NULL) is upgraded and keeps all data."""
    if core.database.is_postgres():
        return                                   # SQLite-only upgrade
    path = os.path.join(tempfile.mkdtemp(), "old.db")
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE merchants(id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT '', phone TEXT UNIQUE NOT NULL,
        upi_id TEXT, city TEXT, plan TEXT NOT NULL DEFAULT 'trial', plan_until INTEGER NOT NULL,
        active INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, last_seen INTEGER);
    CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, merchant_id INTEGER NOT NULL REFERENCES merchants(id)
        ON DELETE CASCADE, device TEXT, created_at INTEGER NOT NULL, last_seen INTEGER);
    CREATE TABLE payments(id INTEGER PRIMARY KEY, merchant_id INTEGER, amount REAL, payer TEXT, app TEXT,
        status TEXT, ts INTEGER, dedupe_key TEXT, received_at INTEGER, UNIQUE(merchant_id, dedupe_key));
    CREATE TABLE subscriptions(id INTEGER PRIMARY KEY, merchant_id INTEGER NOT NULL REFERENCES merchants(id)
        ON DELETE CASCADE, plan TEXT NOT NULL, amount INTEGER NOT NULL, method TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', provider_ref TEXT, payment_ref TEXT, created_at INTEGER NOT NULL, paid_at INTEGER);
    CREATE TABLE otps(phone TEXT PRIMARY KEY);
    INSERT INTO merchants(id, name, phone, upi_id, plan, plan_until, created_at) VALUES (7, 'Old Shop', '9840012345', 'old@okaxis', 'basic', 99999999999999, 1);
    INSERT INTO sessions VALUES ('t', 7, 'x', 1, 1);
    """)
    con.commit(); con.close()
    old, core.DB_PATH = core.DB_PATH, path
    try:
        core.init_db()
        core.init_db()                                                      # running twice is safe
        con = sqlite3.connect(path)
        info = {r[1]: r for r in con.execute("PRAGMA table_info(merchants)")}
        assert info["phone"][3] == 0 and "google_sub" in info and "on_trial" in info
        assert con.execute("SELECT name, phone, plan FROM merchants WHERE id=7").fetchone() == ("Old Shop", "9840012345", "basic")
        assert "merchants_old" not in str(con.execute("SELECT sql FROM sqlite_master").fetchall())
        assert con.execute("SELECT count(*) FROM sqlite_master WHERE name='otps'").fetchone()[0] == 0
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("INSERT INTO subscriptions(merchant_id, plan, amount, method, created_at) VALUES (7,'basic',54,'link',1)")
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        con.close()
    finally:
        core.DB_PATH = old


def test_plan_is_fixed_in_code():
    """The admin page can't change the plan. Old prices saved in plan_settings are ignored."""
    assert not hasattr(core, "admin_set_plan")
    with core.db() as c:
        c.execute("INSERT INTO plan_settings(plan_id, price, rzp_plan_id, link, updated_at) VALUES ('basic', 54, NULL, 'https://rzp.io/rzp/old', 1)")
    try:
        p = core.get_plans()["basic"]
        assert (p["price"], p["per_day"], p["link"]) == (30, "1", "https://rzp.io/rzp/WO6mEyFr")
    finally:
        with core.db() as c:
            c.execute("DELETE FROM plan_settings")


def test_admin_stats_counts():
    s = core.admin_stats()
    assert s["total_users"] == sum(s["by_status"].values())
    assert {p["id"] for p in s["plans"]} == {"basic"}
    assert "plus" not in s["by_status"]
    assert s["setup"]["database"] in ("sqlite", "postgres")
    assert s["monthly_income"] >= 0 and s["autopay_on"] >= 1


def test_policy_pages():
    import legal_pages
    for k in ("PAYVORO_LEGAL_NAME", "PAYVORO_SUPPORT_EMAIL", "PAYVORO_SUPPORT_PHONE", "PAYVORO_ADDRESS", "PAYVORO_JURISDICTION"):
        os.environ.pop(k, None)
    assert len(legal_pages.missing_details()) == 5
    assert core.setup_status()["legal_missing"]
    os.environ.update(PAYVORO_LEGAL_NAME="Test <Shop>", PAYVORO_SUPPORT_EMAIL="help@example.com",
                      PAYVORO_SUPPORT_PHONE="9000000000", PAYVORO_ADDRESS="1 Main Road",
                      PAYVORO_JURISDICTION="Erode, Tamil Nadu")
    try:
        assert legal_pages.missing_details() == []
        t = legal_pages.terms_html(30, "1", 3)
        assert "₹30 per month" in t and "₹1 per day" in t and "3 days" in t and "Erode, Tamil Nadu" in t
        assert "Test &lt;Shop&gt;" in t and "<Shop>" not in t                 # details are HTML-escaped
        assert "not</b> receive, hold, move, settle or verify" in t
        r = legal_pages.refund_html(30, "1", 3)
        assert "same payment method" in r and "7 days" in r and "help@example.com" in r
        pv = legal_pages.privacy_html()
        assert "not sent to our server" in pv and "Digital Personal Data Protection Act" in pv
        assert "Grievance officer" in legal_pages.contact_html()
    finally:
        for k in ("PAYVORO_LEGAL_NAME", "PAYVORO_SUPPORT_EMAIL", "PAYVORO_SUPPORT_PHONE", "PAYVORO_ADDRESS", "PAYVORO_JURISDICTION"):
            os.environ.pop(k, None)


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"All {len(tests)} tests passed")


# ---------------- v4.1 admin features ----------------
def test_admin_edit_notes_and_message():
    mid, tok = new_shop("edit@gmail.com", "Edit Shop", "edit@okaxis")
    d = core.admin_edit_merchant(mid, {"name": "Edit Stores", "city": "Erode", "notes": "Pays late", "message": "Please update the app"})
    m = d["merchant"]
    assert (m["name"], m["city"], m["notes"], m["message"]) == ("Edit Stores", "Erode", "Pays late", "Please update the app")
    assert d["log"][0]["action"] == "edited" and "private notes" in d["log"][0]["detail"]
    expect_error(lambda: core.admin_edit_merchant(mid, {"upi_id": "bad upi"}), 400)
    expect_error(lambda: core.admin_edit_merchant(mid, {"email": "ravi@gmail.com"}), 409)    # someone else's
    core.admin_edit_merchant(mid, {"message": ""})                                              # cleared
    core.admin_set_notice("New version 1.0.2 is on Play Store")
    with core.db() as c:
        row = c.execute("SELECT * FROM merchants WHERE id=?", (mid,)).fetchone()
    assert core.app_notice_for(row) == "New version 1.0.2 is on Play Store"
    core.admin_edit_merchant(mid, {"message": "Hi"})
    with core.db() as c:
        row = c.execute("SELECT * FROM merchants WHERE id=?", (mid,)).fetchone()
    assert core.app_notice_for(row) == "Hi\n\nNew version 1.0.2 is on Play Store"
    core.admin_set_notice("")
    assert core.get_notice() == ""


def test_admin_free_days_end_plan_logout_delete():
    mid, tok = new_shop("days@gmail.com", "Days Shop", "days@okaxis")
    expect_error(lambda: core.admin_give_days(mid, 5, ""), 400)               # reason needed
    expect_error(lambda: core.admin_give_days(mid, 500, "too many"), 400)
    m = core.admin_give_days(mid, 7, "Shop opening offer")["merchant"]
    assert m["status"] == "basic" and m["plan_until"] > core.now_ms() + 6 * DAY
    assert me(mid)["can_announce"]
    assert m["ending_soon"] is False
    m = core.admin_end_plan(mid, "Asked to stop")["merchant"]
    assert m["status"] == "expired" and not me(mid)["can_announce"]           # voice stops at once
    assert core.admin_logout_devices(mid) == 1
    expect_error(lambda: core.merchant_by_token(tok), 401)
    acts = [l["action"] for l in core.admin_recent_log(10, mid)]
    assert acts[:3] == ["logged_out", "plan_ended", "free_days"]
    core.admin_delete_merchant(mid)                                           # never paid → can delete
    assert all(x["id"] != mid for x in core.admin_list_merchants())
    assert core.admin_recent_log(1)[0]["action"] == "deleted"


def test_paid_merchant_cannot_be_deleted_and_charges_are_counted():
    mid, _ = new_shop("charged@gmail.com", "Charge Shop", "charge@okaxis")
    sid = core.create_manual_payment(mid, "basic")["request_id"]
    assert core.activate_subscription(sid, "manual")
    row = next(r for r in core.admin_list_merchants() if r["id"] == mid)
    assert (row["paid_total"], row["paid_count"]) == (30, 1)
    expect_error(lambda: core.admin_delete_merchant(mid), 409)
    month = core.admin_charts()["income"][-1]["value"]
    assert month >= 30 and len(core.admin_charts()["signups"]) == 30
    assert core.admin_charts()["signups"][-1]["value"] >= 1


def test_every_monthly_autopay_charge_is_counted_once():
    use_api(True)
    try:
        mid, _ = new_shop("monthly@gmail.com", "Monthly Shop", "monthly@okaxis")
        core.create_subscription(mid, "basic")
        ref = ref_of(mid, "basic")
        rsub = {"id": ref, "plan_id": "plan_B", "current_end": (core.now_ms() + 30 * DAY) // 1000}
        hook("subscription.charged", rsub, payment={"id": "pay_1", "amount": 3000}, eid="ev_m1")
        hook("subscription.charged", rsub, payment={"id": "pay_1", "amount": 3000}, eid="ev_m1b")  # same payment again
        hook("subscription.charged", rsub, payment={"id": "pay_2", "amount": 3000}, eid="ev_m2")   # next month
        row = next(r for r in core.admin_list_merchants() if r["id"] == mid)
        assert (row["paid_total"], row["paid_count"]) == (60, 2)
    finally:
        use_api(False)


def test_bulk_stop_start_and_stats():
    a, ta = new_shop("bulk1@gmail.com", "Bulk One", "b1@okaxis")
    b, tb = new_shop("bulk2@gmail.com", "Bulk Two", "b2@okaxis")
    assert core.admin_bulk([a, b], "stop") == 2
    assert {r["id"]: r["status"] for r in core.admin_list_merchants()}[a] == "stopped"
    expect_error(lambda: core.merchant_by_token(tb), 401)
    core.admin_bulk([a, b], "start")
    assert {r["id"]: r["status"] for r in core.admin_list_merchants()}[b] != "stopped"
    expect_error(lambda: core.admin_bulk([a], "delete"), 400)
    s = core.admin_stats()
    assert {"ending_soon", "active_today", "not_set_up"} <= set(s)


# ---------------------------------------------------------------- v4.2: AutoPay check with Razorpay (no webhook)
import urllib.parse  # noqa: E402

import autopay_sync  # noqa: E402


class FakeRazorpay:
    """Razorpay's GET API for subscriptions, customers, invoices and payments."""

    def __init__(self):
        self.subs, self.customers, self.invoices, self.payments, self.calls = {}, {}, {}, {}, []

    def add_sub(self, sid, status, created_s, customer=None, notes=None, paid=(), current_end=None, start_at=None):
        self.subs[sid] = {"id": sid, "plan_id": "plan_B", "status": status, "created_at": created_s,
                          "customer_id": customer, "notes": notes or {}, "paid_count": len(paid),
                          "current_end": current_end, "start_at": start_at or created_s, "short_url": f"https://rzp.io/i/{sid}"}
        self.invoices[sid] = [{"id": f"inv_{p}", "payment_id": p, "status": "paid", "amount_paid": 3000,
                               "paid_at": created_s + i * 30 * 86400} for i, p in enumerate(paid)]

    def __call__(self, method, path, body=None):
        self.calls.append((method, path))
        url = urllib.parse.urlparse(path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        parts = url.path.strip("/").split("/")
        if method == "POST" and parts == ["subscriptions"]:
            sid = f"sub_made{len(self.subs) + 1}"
            self.subs[sid] = {"id": sid, "plan_id": body["plan_id"], "status": "created", "created_at": core.now_ms() // 1000,
                              "notes": body.get("notes") or {}, "paid_count": 0, "short_url": f"https://rzp.io/i/{sid}"}
            self.invoices[sid] = []
            return self.subs[sid]
        if method == "POST" and len(parts) == 3 and parts[2] == "cancel":
            self.subs[parts[1]]["status"] = "cancelled"
            return self.subs[parts[1]]
        if parts == ["subscriptions"]:
            items = [s for s in self.subs.values() if s["created_at"] >= int(q.get("from", 0))
                     and (not q.get("plan_id") or s["plan_id"] == q["plan_id"])]
            items.sort(key=lambda s: -s["created_at"])
            skip, count = int(q.get("skip", 0)), int(q.get("count", 10))
            return {"items": items[skip:skip + count]}
        if parts[0] == "subscriptions":
            return self.subs[parts[1]]
        if parts[0] == "customers":
            return self.customers[parts[1]]
        if parts[0] == "invoices":
            return {"items": self.invoices.get(q["subscription_id"], [])}
        if parts[0] == "payments":
            return self.payments[parts[1]]
        return {}


def with_fake_razorpay(test):
    def run():
        fake = FakeRazorpay()
        old = core.rzp_request
        core.rzp_request = fake
        use_api(True)
        try:
            test(fake)
        finally:
            core.rzp_request = old
            use_api(False)
    run.__name__ = test.__name__
    return run


def row_of(mid):
    with core.db() as c:
        return dict(c.execute("SELECT * FROM merchants WHERE id=?", (mid,)).fetchone())


@with_fake_razorpay
def test_sync_finds_link_autopay_by_customer_email(fake):
    """Merchant set AutoPay on the rzp.io link, the webhook never came. The sync finds it by the customer's email."""
    mid, _ = new_shop("sync1@gmail.com", "Sync One", "sync1@okaxis")
    now_s = core.now_ms() // 1000
    fake.customers["cust_1"] = {"email": "SYNC1@gmail.com", "contact": "+919876500001"}
    fake.add_sub("sub_s1", "authenticated", now_s - 60, customer="cust_1", start_at=now_s + 3 * 86400)
    r = autopay_sync.sync()
    assert r["matched_new"] >= 1                     # (errors = AutoPays from older tests the fake does not know)
    m = me(mid)
    assert m["autopay"] and m["autopay_status"] == "authenticated" and m["on_trial"] and m["can_announce"]
    assert row_of(mid)["autopay_ref"] == "sub_s1" and row_of(mid)["autopay_checked_at"]
    assert autopay_sync.last_sync()["matched_new"] >= 1
    # running again changes nothing and adds no duplicate request
    before = row_of(mid)
    autopay_sync.sync()
    after = row_of(mid)
    assert (before["plan_until"], before["autopay_status"]) == (after["plan_until"], after["autopay_status"])
    with core.db() as c:
        assert c.execute("SELECT COUNT(*) FROM subscriptions WHERE provider_ref='sub_s1'").fetchone()[0] == 1


@with_fake_razorpay
def test_sync_matches_by_upi_id_when_email_differs(fake):
    mid, _ = new_shop("sync2@gmail.com", "Sync Two", "sync2shop@okhdfcbank")
    now_s = core.now_ms() // 1000
    fake.customers["cust_2"] = {"email": "other.person@yahoo.com", "contact": ""}
    fake.payments["pay_s2"] = {"id": "pay_s2", "email": "other.person@yahoo.com", "vpa": "SYNC2SHOP@okhdfcbank"}
    fake.add_sub("sub_s2", "active", now_s - 120, customer="cust_2", paid=["pay_s2"], current_end=now_s + 30 * 86400)
    autopay_sync.sync()
    m = me(mid)
    assert m["autopay_status"] == "active" and m["plan_active"] and not m["on_trial"]
    assert m["plan_until"] == (now_s + 30 * 86400) * 1000
    row = next(r for r in core.admin_list_merchants() if r["id"] == mid)
    assert (row["paid_total"], row["paid_count"]) == (30, 1)


@with_fake_razorpay
def test_monthly_charges_counted_once_and_plan_extended(fake):
    mid, _ = new_shop("sync3@gmail.com", "Sync Three", "sync3@okaxis")
    now_s = core.now_ms() // 1000
    fake.add_sub("sub_s3", "active", now_s - 40 * 86400, notes={"email": "sync3@gmail.com"},
                 paid=["pay_a", "pay_b"], current_end=now_s + 20 * 86400)
    autopay_sync.sync(days=60)
    autopay_sync.sync(days=60)
    row = next(r for r in core.admin_list_merchants() if r["id"] == mid)
    assert (row["paid_total"], row["paid_count"]) == (60, 2)
    assert row["plan_until"] == (now_s + 20 * 86400) * 1000
    # charge dates are Razorpay's, not "now" (for the income chart)
    with core.db() as c:
        times = sorted(r[0] for r in c.execute("SELECT paid_at FROM charges WHERE merchant_id=?", (mid,)).fetchall())
    assert times[0] == (now_s - 40 * 86400) * 1000


@with_fake_razorpay
def test_failed_charge_shows_even_with_old_charges(fake):
    mid, _ = new_shop("sync4@gmail.com", "Sync Four", "sync4@okaxis")
    now_s = core.now_ms() // 1000
    fake.add_sub("sub_s4", "halted", now_s - 35 * 86400, notes={"email": "sync4@gmail.com"},
                 paid=["pay_h1"], current_end=now_s - 5 * 86400)
    autopay_sync.sync(days=60)
    assert me(mid)["autopay_status"] == "halted"
    assert next(r for r in core.admin_list_merchants() if r["id"] == mid)["paid_count"] == 1


@with_fake_razorpay
def test_old_autopay_never_replaces_new_one(fake):
    mid, _ = new_shop("sync5@gmail.com", "Sync Five", "sync5@okaxis")
    now_s = core.now_ms() // 1000
    fake.add_sub("sub_old5", "cancelled", now_s - 20 * 86400, notes={"email": "sync5@gmail.com"}, paid=["pay_o5"])
    fake.add_sub("sub_new5", "active", now_s - 86400, notes={"email": "sync5@gmail.com"}, paid=["pay_n5"],
                 current_end=now_s + 29 * 86400)
    # the old one was known first (webhook long ago)
    with core.db() as c:
        c.insert("INSERT INTO subscriptions(merchant_id, plan, amount, method, provider_ref, created_at) VALUES (?,?,?,?,?,?)",
                 (mid, "basic", 30, "link", "sub_old5", (now_s - 20 * 86400) * 1000))
    autopay_sync.sync(days=60)
    r = row_of(mid)
    assert r["autopay_ref"] == "sub_new5" and r["autopay_status"] == "active"
    assert fake.subs["sub_new5"]["status"] == "active"                 # the new one was not cancelled
    assert next(x for x in core.admin_list_merchants() if x["id"] == mid)["paid_count"] == 2


@with_fake_razorpay
def test_unmatched_autopay_link_and_ignore(fake):
    mid, _ = new_shop("sync6@gmail.com", "Sync Six", "sync6@okaxis")
    now_s = core.now_ms() // 1000
    fake.customers["cust_x"] = {"email": "unknown.buyer@gmail.com", "contact": "9000000006"}
    fake.add_sub("sub_x6", "authenticated", now_s - 30, customer="cust_x", start_at=now_s + 3 * 86400)
    fake.add_sub("sub_y6", "active", now_s - 40, notes={"email": "nobody@nowhere.com"})
    r = autopay_sync.sync()
    assert r["unmatched"] >= 2
    um = {u["rzp_sub_id"]: u for u in autopay_sync.list_unmatched()}
    assert um["sub_x6"]["email"] == "unknown.buyer@gmail.com" and um["sub_x6"]["phone"] == "9000000006"
    autopay_sync.link_unmatched("sub_x6", mid)
    assert me(mid)["autopay_status"] == "authenticated" and me(mid)["on_trial"]
    autopay_sync.ignore_unmatched("sub_y6")
    left = {u["rzp_sub_id"] for u in autopay_sync.list_unmatched()}
    assert "sub_x6" not in left and "sub_y6" not in left
    autopay_sync.sync()                                                # ignored stays ignored
    assert "sub_y6" not in {u["rzp_sub_id"] for u in autopay_sync.list_unmatched()}
    other, _ = new_shop("sync6b@gmail.com", "Sync Six B", "sync6b@okaxis")
    expect_error(lambda: autopay_sync.link_unmatched("sub_x6", other), 409)


@with_fake_razorpay
def test_app_open_checks_only_when_waiting_and_not_too_often(fake):
    mid, tok = new_shop("sync7@gmail.com", "Sync Seven", "sync7@okaxis")
    m = core.merchant_by_token(tok)
    assert autopay_sync.maybe_autocheck(m)["autopay_status"] == ""
    assert fake.calls == []                                            # not waiting for AutoPay → no Razorpay call
    core.create_subscription(mid, "basic")                             # app opened the AutoPay page
    now_s = core.now_ms() // 1000
    fake.add_sub(ref_of(mid, "basic"), "authenticated", now_s, notes={"merchant_id": str(mid)}, start_at=now_s + 3 * 86400)
    m = autopay_sync.maybe_autocheck(core.merchant_by_token(tok))
    assert m["autopay_status"] == "authenticated"
    n = len(fake.calls)
    autopay_sync.maybe_autocheck(core.merchant_by_token(tok))          # again at once → no new call
    assert len(fake.calls) == n


@with_fake_razorpay
def test_admin_cancels_autopay_and_bulk_check(fake):
    mid, _ = new_shop("sync8@gmail.com", "Sync Eight", "sync8@okaxis")
    now_s = core.now_ms() // 1000
    fake.add_sub("sub_s8", "active", now_s - 100, notes={"email": "sync8@gmail.com"}, paid=["pay_s8"],
                 current_end=now_s + 30 * 86400)
    assert core.admin_bulk([mid], "autopay_check") == 1
    assert me(mid)["autopay_status"] == "active"
    expect_error(lambda: autopay_sync.cancel_merchant_autopay(mid, ""), 400)
    d = autopay_sync.cancel_merchant_autopay(mid, "merchant asked")
    assert d["merchant"]["autopay_status"] == "cancelled" and fake.subs["sub_s8"]["status"] == "cancelled"
    assert me(mid)["plan_active"]                                      # paid days keep working
    assert any(l["action"] == "autopay_cancelled" for l in d["log"])
    expect_error(lambda: autopay_sync.cancel_merchant_autopay(mid, "again"), 400)


def test_sync_needs_api_keys():
    use_api(False)
    expect_error(lambda: autopay_sync.sync(), 503)
