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
    assert [p["per_day"] for p in plans["plans"]] == ["1.8", "3.5"] and plans["trial_days"] == 3

    now = main.core.now_ms()
    batch = {"payments": [{"amount": 500, "app": "gpay", "timestamp": now, "dedupe_key": "a"}]}
    assert c.post("/api/payments", headers=H, json=batch).json()["inserted"] == 1

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
    assert {"basic", "plus", "trial", "expired", "no_plan", "stopped"} <= set(d["stats"]["by_status"])
    m = d["merchants"][0]
    assert "google_sub" not in m and m["status"] in d["stats"]["by_status"]
    assert c.get(f"/admin/merchants/{m['id']}/subscriptions", headers=A).status_code == 200

    # change AutoPay amount (no Razorpay keys in this test -> a link is needed)
    r = c.put("/admin/plans/plus", headers=A, json={"price": 150, "link": "https://rzp.io/rzp/plus150"}).json()
    assert r["plan"]["price"] == 150 and r["plan"]["per_day"] == "5" and not r["warning"]
    assert {p["id"]: p for p in c.get("/api/plans").json()["plans"]}["plus"]["price"] == 150
    assert c.put("/admin/plans/plus", headers=A, json={"price": 0}).status_code == 422
    assert c.put("/admin/plans/gold", headers=A, json={"price": 10}).status_code == 400
    c.put("/admin/plans/plus", headers=A, json={"price": 105, "link": "https://rzp.io/rzp/qTp7E5Ai"})
