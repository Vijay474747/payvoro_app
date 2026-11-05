"""End-to-end test of the web routes. Run: pip install pytest httpx && pytest"""
import os
import tempfile

os.environ["PAYVORO_DB"] = os.path.join(tempfile.mkdtemp(), "web.db")
os.environ["PAYVORO_ADMIN_KEY"] = "secret"
os.environ["PAYVORO_DEV"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

c = TestClient(main.app)
A = {"X-Admin-Key": "secret"}


def test_full_flow():
    assert c.get("/admin/merchants", headers={"X-Admin-Key": "bad"}).status_code == 401
    assert c.post("/api/auth/google", json={"id_token": "not-a-real-token"}).status_code in (401, 500)

    r = c.post("/api/auth/google", json={"id_token": "dev:ravi@gmail.com", "device": "test"}).json()
    H = {"Authorization": "Bearer " + r["token"]}
    assert r["is_new"] is True and r["merchant"]["needs_plan"] is True

    assert c.patch("/api/me", headers=H, json={"name": "Ravi Stores", "upi_id": "ravi@okaxis"}).json()["name"] == "Ravi Stores"
    plans = c.get("/api/plans").json()
    assert [p["per_day"] for p in plans["plans"]] == ["1"] and plans["trial_days"] == 3

    now = main.core.now_ms()
    batch = {"payments": [{"amount": 500, "app": "gpay", "timestamp": now, "dedupe_key": "a"}]}
    assert c.post("/api/payments", headers=H, json=batch).json()["inserted"] == 0   # not stored any more

    auto = c.post("/api/subscribe", headers=H, json={"plan": "basic"}).json()
    assert auto["method"] == "link" and auto["url"].startswith("https://rzp.io/")

    manual = c.post("/api/subscribe/manual", headers=H, json={"plan": "basic"}).json()
    pending = c.get("/admin/subscriptions?status=pending&method=manual", headers=A).json()
    assert [p["id"] for p in pending] == [manual["request_id"]]
    assert c.post(f"/admin/subscriptions/{manual['request_id']}/approve", headers=A).json()["activated"]
    me = c.get("/api/me", headers=H).json()
    assert me["plan"] == "basic" and me["plan_active"] and not me["needs_plan"]

    c.post("/api/auth/logout", headers=H)
    assert c.get("/api/me", headers=H).status_code == 401
    assert "Payvoro Admin" in c.get("/admin").text


def test_dashboard_and_plan_price():
    assert c.get("/").status_code == 200 and "Payvoro" in c.get("/").text
    assert c.get("/admin/dashboard").status_code == 401
    d = c.get("/admin/dashboard", headers=A).json()
    assert d["webhook_url"].endswith("/api/razorpay/webhook")
    assert d["stats"]["total_users"] == len(d["merchants"]) >= 1
    assert {"basic", "trial", "expired", "no_plan", "stopped"} == set(d["stats"]["by_status"])
    m = d["merchants"][0]
    assert "google_sub" not in m and m["status"] in d["stats"]["by_status"]
    assert c.get(f"/admin/merchants/{m['id']}/subscriptions", headers=A).status_code == 200

    # the plan is fixed: no route to change it any more
    assert c.put("/admin/plans/basic", headers=A, json={"price": 99}).status_code in (404, 405)
    assert {p["id"]: p for p in c.get("/api/plans").json()["plans"]}["basic"]["price"] == 30
    assert c.get(f"/admin/merchants/{m['id']}/payments", headers=A).status_code == 404   # customer payments not kept


def test_policy_pages():
    for path, words in (("/terms", "Terms of Service"), ("/privacy", "Privacy Policy"),
                        ("/refund", "Refund"), ("/contact", "Grievance")):
        r = c.get(path)
        assert r.status_code == 200 and words in r.text
    assert "₹30 per month" in c.get("/refund").text
    assert 'href="/terms"' in c.get("/").text


def test_admin_v42_routes():
    page = c.get("/admin").text
    assert "+1 month" not in page and "setPlan" not in page and "extend_months" not in page   # removed in v4.2
    d = c.get("/admin/dashboard", headers=A).json()
    assert "unmatched" in d and "autopay_sync" in d
    mid = d["merchants"][0]["id"]
    # no API keys in tests → the Razorpay check explains what to set
    assert c.post("/admin/autopay/sync", headers=A).status_code == 503
    assert c.post(f"/admin/merchants/{mid}/autopay-check", headers=A).status_code == 503
    assert c.post(f"/admin/merchants/{mid}/cancel-autopay", headers=A, json={"reason": "test"}).status_code in (400, 503)
    # the cron needs CRON_SECRET or the admin key
    assert c.get("/api/cron/autopay-sync").status_code == 401
    assert c.get("/api/cron/autopay-sync", headers=A).json() == {"skipped": "Razorpay API keys are not set"}
    # old "+1 month" / plan fields are ignored by the server (only free days with a reason change the plan)
    before = c.get(f"/admin/merchants/{mid}", headers=A).json()["merchant"]["plan_until"]
    c.patch(f"/admin/merchants/{mid}", headers=A, json={"extend_months": 1, "plan": "basic"})
    assert c.get(f"/admin/merchants/{mid}", headers=A).json()["merchant"]["plan_until"] == before
    r = c.post(f"/admin/merchants/{mid}/free-days", headers=A, json={"days": 2, "reason": "test days"}).json()
    assert r["merchant"]["plan_until"] > before
