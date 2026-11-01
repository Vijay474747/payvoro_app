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
