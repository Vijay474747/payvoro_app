"""
Payvoro server – web routes. All logic lives in core.py.

Run (test mode: login token "dev:<email>" works without Google):
    pip install -r requirements.txt
    PAYVORO_DEV=1 PAYVORO_ADMIN_KEY=secret uvicorn main:app --host 0.0.0.0 --port 8000

Admin page: http://<server>:8000/admin

On Vercel: this file is found by itself (FastAPI app named "app" in main.py). See README "Deploy on Vercel".
"""
import logging
import os
import secrets
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

import autopay_sync
import core
import legal_pages
from admin_page import ADMIN_HTML, HOME_HTML
from core import AppError

log = logging.getLogger("payvoro")
ADMIN_KEY = os.getenv("PAYVORO_ADMIN_KEY", "")

app = FastAPI(title="Payvoro Server", version="4.2.0")

_db_ready = False


def ensure_db():
    """Creates tables once per server start. On Vercel a failed start is retried on the next request."""
    global _db_ready
    if not _db_ready:
        core.init_db()
        _db_ready = True


try:
    ensure_db()
except Exception:
    log.exception("database not ready yet - will retry on the next request")


@app.middleware("http")
async def db_ready(request: Request, call_next):
    if not _db_ready:
        try:
            ensure_db()
        except Exception:
            log.exception("database connection failed")
            return JSONResponse(status_code=503, content={"detail": "Database is not reachable. Check DATABASE_URL."})
    return await call_next(request)


@app.exception_handler(AppError)
def app_error(_req: Request, e: AppError):
    return JSONResponse(status_code=e.status, content={"detail": e.detail})


# ---------- auth ----------
def admin_only(x_admin_key: str = Header("")):
    key = ADMIN_KEY or ("change-me" if core.DEV else "")
    if not key:
        raise HTTPException(503, "Set PAYVORO_ADMIN_KEY on the server first")
    if not x_admin_key or not secrets.compare_digest(x_admin_key.encode(), key.encode()):
        raise HTTPException(401, "Wrong admin key")


def bearer(authorization: str = Header("")) -> str:
    return authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""


def current_merchant(token: str = Depends(bearer)):
    return core.merchant_by_token(token)


# ---------- models ----------
class GoogleIn(BaseModel):
    id_token: str
    device: Optional[str] = None


class MeUpdate(BaseModel):
    name: Optional[str] = None
    upi_id: Optional[str] = None


class PaymentIn(BaseModel):
    amount: float = Field(gt=0)
    payer: Optional[str] = None
    app: str
    status: str = "SUCCESS"
    timestamp: int
    dedupe_key: str
    utr: Optional[str] = None
    source: str = "app"
    bank_confirmed: bool = False


class PaymentBatch(BaseModel):
    payments: List[PaymentIn] = Field(max_length=500)


class SubscribeIn(BaseModel):
    plan: str


class MerchantIn(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    upi_id: Optional[str] = None
    city: Optional[str] = None
    plan: str = "none"
    months: int = Field(default=1, ge=1, le=36)


class MerchantUpdate(BaseModel):
    """Stop / start, edit shop details, private notes, message shown in this merchant's app.
    (The plan dropdown and "+1 month" were removed from the admin page – use free days with a reason.)"""
    active: Optional[bool] = None
    name: Optional[str] = Field(default=None, max_length=60)
    email: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=20)
    upi_id: Optional[str] = Field(default=None, max_length=120)
    city: Optional[str] = Field(default=None, max_length=60)
    notes: Optional[str] = Field(default=None, max_length=1000)
    message: Optional[str] = Field(default=None, max_length=1000)


class DaysIn(BaseModel):
    days: int = Field(ge=1, le=90)
    reason: str = Field(min_length=3, max_length=200)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


class BulkIn(BaseModel):
    ids: List[int] = Field(min_length=1, max_length=1000)
    action: str


class NoticeIn(BaseModel):
    text: str = Field(default="", max_length=500)


class LinkAutopayIn(BaseModel):
    rzp_sub_id: str = Field(min_length=5, max_length=60)
    merchant_id: int


class IgnoreAutopayIn(BaseModel):
    rzp_sub_id: str = Field(min_length=5, max_length=60)


# ---------- app API ----------
@app.get("/", response_class=HTMLResponse)
def home():
    return HOME_HTML


def _basic_plan():
    """Live price of the only plan (the admin page can change it)."""
    try:
        p = core.get_plans()["basic"]
        return int(p["price"]), str(p["per_day"])
    except Exception:
        p = core.PLANS["basic"]
        return int(p["price"]), str(p["per_day"])


# ---------- public policy pages (Razorpay checks these) ----------
@app.get("/terms", response_class=HTMLResponse)
def terms_page():
    price, per_day = _basic_plan()
    return legal_pages.terms_html(price, per_day, core.TRIAL_DAYS)


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page():
    return legal_pages.privacy_html()


@app.get("/refund", response_class=HTMLResponse)
def refund_page():
    price, per_day = _basic_plan()
    return legal_pages.refund_html(price, per_day, core.TRIAL_DAYS)


@app.get("/contact", response_class=HTMLResponse)
def contact_page():
    return legal_pages.contact_html()


@app.get("/api/health")
def health():
    return {"ok": True, "time": core.now_ms(), "database": core.setup_status()["database"]}


@app.post("/api/auth/google")
def google_login(body: GoogleIn):
    return core.login_google(body.id_token, body.device)


@app.post("/api/auth/logout")
def logout(token: str = Depends(bearer)):
    core.logout(token)
    return {"ok": True}


@app.get("/api/me")
def me(m=Depends(current_merchant)):
    # Waiting for AutoPay (or a charge is due)? Ask Razorpay now, so it is verified without the webhook.
    m = autopay_sync.maybe_autocheck(m)
    # "notice": message for this merchant + notice for everyone, shown on the app's Home screen
    return {**core.public_merchant(m), "notice": core.app_notice_for(m)}


@app.patch("/api/me")
def update_me(body: MeUpdate, m=Depends(current_merchant)):
    return core.update_me(m["id"], body.name, body.upi_id)


@app.get("/api/plans")
def plans():
    return {"plans": core.public_plans(), "trial_days": core.TRIAL_DAYS, "grace_days": core.GRACE_DAYS}


@app.post("/api/subscribe")
def subscribe(body: SubscribeIn, m=Depends(current_merchant)):
    """Starts UPI AutoPay. Returns the Razorpay page to open."""
    return core.create_subscription(m["id"], body.plan)


@app.post("/api/subscribe/manual")
def subscribe_manual(body: SubscribeIn, m=Depends(current_merchant)):
    """Backup: one month by razorpay.me link, approved by admin."""
    return core.create_manual_payment(m["id"], body.plan)


@app.post("/api/payments")
def add_payments(m=Depends(current_merchant)):
    """Old app versions send customer payments here. They are NOT stored any more (Razorpay review)."""
    return {"inserted": 0, **{k: v for k, v in core.public_merchant(m).items() if k.startswith("plan") or k == "can_announce"}}


# ---------- payments (Razorpay) ----------
@app.post("/api/razorpay/webhook")
async def razorpay_webhook(request: Request, x_razorpay_signature: str = Header(""),
                           x_razorpay_event_id: Optional[str] = Header(None)):
    return core.handle_razorpay_webhook(await request.body(), x_razorpay_signature, x_razorpay_event_id)


@app.get("/api/cron/autopay-sync")
def cron_autopay_sync(authorization: str = Header(""), x_admin_key: str = Header("")):
    """Daily AutoPay check (Vercel Cron, see vercel.json). Vercel sends "Authorization: Bearer <CRON_SECRET>"."""
    secret = os.getenv("CRON_SECRET", "")
    ok = (secret and secrets.compare_digest(authorization.encode(), f"Bearer {secret}".encode())) or \
         (ADMIN_KEY and x_admin_key and secrets.compare_digest(x_admin_key.encode(), ADMIN_KEY.encode()))
    if not ok:
        raise HTTPException(401, "Not allowed")
    if not core.razorpay_ready():
        return {"skipped": "Razorpay API keys are not set"}
    return autopay_sync.sync(days=45, source="daily")


@app.get("/pay/done", response_class=HTMLResponse)
def pay_done():
    return ("<html><body style='font-family:sans-serif;text-align:center;padding:40px'>"
            "<h2>Thank you!</h2><p>AutoPay is set. Go back to the Payvoro app.</p></body></html>")


# ---------- admin API ----------
@app.get("/admin/dashboard", dependencies=[Depends(admin_only)])
def dashboard(request: Request):
    """Everything the admin page shows, in one call."""
    merchants = core.admin_list_merchants()
    base = str(request.base_url).rstrip("/")
    if request.headers.get("x-forwarded-proto") == "https":
        base = base.replace("http://", "https://", 1)
    return {
        "stats": core.admin_stats(merchants),
        "merchants": merchants,
        "pending": core.admin_list_subscriptions("pending", "manual"),
        "recent": core.admin_list_subscriptions(limit=12),
        "webhook_url": base + "/api/razorpay/webhook",
        "charts": core.admin_charts(),
        "log": core.admin_recent_log(40),
        "notice": core.get_notice(),
        "autopay_sync": autopay_sync.last_sync(),
        "unmatched": autopay_sync.list_unmatched(),
    }


@app.get("/admin/stats", dependencies=[Depends(admin_only)])
def stats():
    return core.admin_stats()


@app.get("/admin/merchants/{mid}/subscriptions", dependencies=[Depends(admin_only)])
def merchant_subscriptions(mid: int):
    return core.admin_list_subscriptions(merchant_id=mid, limit=100)


@app.get("/admin/merchants", dependencies=[Depends(admin_only)])
def list_merchants():
    return core.admin_list_merchants()


@app.post("/admin/merchants", dependencies=[Depends(admin_only)])
def create_merchant(body: MerchantIn):
    return core.admin_create_merchant(body.name, body.email, body.phone, body.upi_id, body.city, body.plan, body.months)


@app.get("/admin/merchants/{mid}", dependencies=[Depends(admin_only)])
def merchant_detail(mid: int):
    return core.admin_merchant_detail(mid)


@app.patch("/admin/merchants/{mid}", dependencies=[Depends(admin_only)])
def update_merchant(mid: int, body: MerchantUpdate):
    if body.active is not None:
        core.admin_update_merchant(mid, body.active, None, None)
    fields = body.model_dump(exclude={"active"}, exclude_none=True)
    return core.admin_edit_merchant(mid, fields) if fields else core.admin_merchant_detail(mid)


@app.delete("/admin/merchants/{mid}", dependencies=[Depends(admin_only)])
def delete_merchant(mid: int):
    core.admin_delete_merchant(mid)
    return {"ok": True}


@app.post("/admin/merchants/{mid}/free-days", dependencies=[Depends(admin_only)])
def free_days(mid: int, body: DaysIn):
    return core.admin_give_days(mid, body.days, body.reason)


@app.post("/admin/merchants/{mid}/end-plan", dependencies=[Depends(admin_only)])
def end_plan(mid: int, body: ReasonIn):
    return core.admin_end_plan(mid, body.reason)


@app.post("/admin/merchants/{mid}/logout", dependencies=[Depends(admin_only)])
def logout_devices(mid: int):
    return {"logged_out": core.admin_logout_devices(mid)}


@app.post("/admin/bulk", dependencies=[Depends(admin_only)])
def bulk(body: BulkIn):
    return {"done": core.admin_bulk(body.ids, body.action)}


@app.put("/admin/notice", dependencies=[Depends(admin_only)])
def set_notice(body: NoticeIn):
    return {"notice": core.admin_set_notice(body.text)}


# ---------- AutoPay check with Razorpay ----------
@app.post("/admin/autopay/sync", dependencies=[Depends(admin_only)])
def admin_autopay_sync(days: int = 45):
    return autopay_sync.sync(days=max(1, min(days, 365)), source="admin")


@app.post("/admin/merchants/{mid}/autopay-check", dependencies=[Depends(admin_only)])
def admin_autopay_check(mid: int):
    report = autopay_sync.sync(merchant_id=mid, days=90, source="admin")
    return {"report": report, **core.admin_merchant_detail(mid)}


@app.post("/admin/merchants/{mid}/cancel-autopay", dependencies=[Depends(admin_only)])
def admin_cancel_autopay(mid: int, body: ReasonIn):
    return autopay_sync.cancel_merchant_autopay(mid, body.reason)


@app.post("/admin/autopay/link", dependencies=[Depends(admin_only)])
def admin_link_autopay(body: LinkAutopayIn):
    return autopay_sync.link_unmatched(body.rzp_sub_id, body.merchant_id)


@app.post("/admin/autopay/ignore", dependencies=[Depends(admin_only)])
def admin_ignore_autopay(body: IgnoreAutopayIn):
    return autopay_sync.ignore_unmatched(body.rzp_sub_id)


@app.get("/admin/log", dependencies=[Depends(admin_only)])
def admin_log(limit: int = 100):
    return core.admin_recent_log(limit)




@app.get("/admin/subscriptions", dependencies=[Depends(admin_only)])
def list_subscriptions(status: Optional[str] = None, method: Optional[str] = None):
    return core.admin_list_subscriptions(status, method)


@app.post("/admin/subscriptions/{sid}/approve", dependencies=[Depends(admin_only)])
def approve(sid: int):
    return {"activated": core.activate_subscription(sid, "manual")}


@app.post("/admin/subscriptions/{sid}/reject", dependencies=[Depends(admin_only)])
def reject(sid: int):
    core.admin_reject_subscription(sid)
    return {"ok": True}


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return ADMIN_HTML
