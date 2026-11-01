"""
Public policy pages for Payvoro: /terms, /privacy, /refund, /contact.

Razorpay checks these pages before it gives live API keys
(refund/cancellation policy, terms, privacy policy and real contact details).

Fill your details on Vercel → Settings → Environment Variables, then Redeploy:
  PAYVORO_LEGAL_NAME      your name or business name (as on your PAN / KYC)
  PAYVORO_SUPPORT_EMAIL   support email
  PAYVORO_SUPPORT_PHONE   support phone number
  PAYVORO_ADDRESS         full postal address
  PAYVORO_JURISDICTION    city for courts, e.g. "Erode, Tamil Nadu"
  PAYVORO_GRIEVANCE_NAME  grievance officer name (default: same as PAYVORO_LEGAL_NAME)
"""
import html
import os

EFFECTIVE_DATE = "1 November 2026"
NOT_SET = "[not set yet]"


def _env(name: str, default: str = NOT_SET) -> str:
    return html.escape(os.getenv(name, "").strip() or default)


def details() -> dict:
    name = _env("PAYVORO_LEGAL_NAME")
    return {
        "name": name,
        "email": _env("PAYVORO_SUPPORT_EMAIL"),
        "phone": _env("PAYVORO_SUPPORT_PHONE"),
        "address": _env("PAYVORO_ADDRESS"),
        "city": _env("PAYVORO_JURISDICTION"),
        "officer": _env("PAYVORO_GRIEVANCE_NAME", os.getenv("PAYVORO_LEGAL_NAME", "").strip() or NOT_SET),
    }


def missing_details() -> list:
    """For the admin setup checklist: which contact details are still empty."""
    keys = ["PAYVORO_LEGAL_NAME", "PAYVORO_SUPPORT_EMAIL", "PAYVORO_SUPPORT_PHONE", "PAYVORO_ADDRESS",
            "PAYVORO_JURISDICTION"]
    return [k for k in keys if not os.getenv(k, "").strip()]


_STYLE = """
:root{--brand:#5b3fe8;--brand-d:#3a22b8;--ink:#16141f;--mute:#6b6880;--bg:#f6f5fb;--card:#fff;--line:#ebe9f3}
@media (prefers-color-scheme:dark){:root{--ink:#ecebf3;--mute:#a7a4b8;--bg:#121019;--card:#1c1a26;--line:#2c2938}}
*{box-sizing:border-box}
body{margin:0;font:16px/1.65 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg)}
header{background:linear-gradient(160deg,var(--brand-d),var(--brand));color:#fff;padding:28px 16px}
header a{color:#fff;text-decoration:none;font-weight:800;font-size:20px}
header h1{margin:8px 0 0;font-size:clamp(24px,5vw,32px);line-height:1.2}
main{max-width:820px;margin:0 auto;padding:20px 16px 40px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px 22px}
h2{font-size:19px;margin:26px 0 6px}h2:first-child{margin-top:0}
p,li{margin:6px 0}ul{padding-left:22px}.mute{color:var(--mute);font-size:14px}
.box{border-left:4px solid var(--brand);padding:8px 14px;margin:12px 0;background:color-mix(in srgb,var(--brand) 8%,transparent);border-radius:6px}
nav{display:flex;flex-wrap:wrap;gap:8px 18px;justify-content:center;padding:18px 16px;font-size:14px}
nav a{color:var(--mute)}
"""


def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · Payvoro</title>
<style>{_STYLE}</style></head><body>
<header><a href="/">Payvoro</a><h1>{title}</h1></header>
<main><div class="card">{body}</div><p class="mute">Effective date: {EFFECTIVE_DATE}</p></main>
<nav><a href="/">Home</a><a href="/terms">Terms of Service</a><a href="/privacy">Privacy Policy</a>
<a href="/refund">Refund &amp; Cancellation</a><a href="/contact">Contact &amp; Grievance</a></nav>
</body></html>"""


def _contact_block(d: dict) -> str:
    return f"""<ul>
<li><b>Business / owner:</b> {d['name']}</li>
<li><b>Grievance officer:</b> {d['officer']}</li>
<li><b>Email:</b> {d['email']}</li>
<li><b>Phone:</b> {d['phone']}</li>
<li><b>Address:</b> {d['address']}</li>
</ul>"""


def terms_html(price: int, per_day: str, trial_days: int) -> str:
    d = details()
    body = f"""
<p>These Terms of Service ("Terms") are an agreement between you and <b>{d['name']}</b>, who runs the
Payvoro app and website ("Payvoro", "we", "us"). By creating an account or using Payvoro, you agree to these Terms.
If you do not agree, please do not use Payvoro.</p>

<h2>1. What Payvoro is</h2>
<p>Payvoro is an Android app that turns the merchant's own phone into a "sound box". When a payment
notification from a UPI app or a bank SMS arrives <b>on your phone</b>, Payvoro reads it and speaks the amount aloud.</p>
<div class="box"><b>What Payvoro is not.</b> Payvoro is not a bank, a payment app, a payment aggregator or a payment gateway.
Payvoro does <b>not</b> receive, hold, move, settle or verify your customers' money. Your customers pay you directly
through your own UPI ID, and the money goes straight to your own bank account.</div>

<h2>2. Who can use Payvoro</h2>
<ul>
<li>You must be at least 18 years old and able to enter into a binding contract under Indian law.</li>
<li>You must use Payvoro for a lawful business in India, with your own UPI ID and your own bank account.</li>
<li>You need a Google account to log in.</li>
</ul>

<h2>3. Your account</h2>
<ul>
<li>Give true details (shop name, UPI ID). Keep your Google account and phone secure.</li>
<li>You are responsible for everything done through your account.</li>
<li>Tell us at once if you think someone else is using your account.</li>
</ul>

<h2>4. Subscription and price</h2>
<ul>
<li>Payvoro has one plan: <b>Basic</b>, shown as <b>₹{per_day} per day</b> and charged as <b>₹{price} per month</b>.</li>
<li>Your first plan has a <b>free trial of {trial_days} days</b>. No money is taken during the trial.</li>
<li>The monthly fee is collected by <b>UPI AutoPay</b> (a recurring mandate) through our payment partner, Razorpay.
You approve the mandate in your own UPI app. After the trial, the fee is charged every month until you cancel.</li>
<li>Prices include applicable taxes unless we say otherwise.</li>
<li>If we change the price, we will tell you in the app or by email before the change. A running AutoPay keeps
its old amount; the new price applies only when you start a new plan.</li>
</ul>

<h2>5. Cancellation and refunds</h2>
<p>You can cancel any time. Cancellation and refunds follow our
<a href="/refund">Refund &amp; Cancellation Policy</a>, which is part of these Terms.</p>

<h2>6. Important limits of the service</h2>
<ul>
<li>Payvoro depends on your phone: notification access, internet, battery settings, the phone maker's settings,
your text-to-speech voice and the UPI or bank app showing a notification. If any of these fail, an alert can be
<b>late, missed, or wrong</b>.</li>
<li>A Payvoro voice alert is <b>not proof of payment</b>. For large amounts, or if you have any doubt,
check your bank app or bank statement before you hand over goods.</li>
<li>We are not responsible for a loss caused by relying only on a Payvoro alert, a fake or edited notification
shown by someone else, or a payment that was later reversed by a bank.</li>
</ul>

<h2>7. Fair use</h2>
<p>You must not: use Payvoro for anything illegal or fraudulent; copy, resell, rent or sub-license Payvoro;
reverse-engineer or attack the app or our servers; or use Payvoro to collect other people's data.</p>

<h2>8. Your data</h2>
<p>How we handle your data is explained in our <a href="/privacy">Privacy Policy</a>.
In short: your customers' payment alerts stay on your phone and are not sent to our server.</p>

<h2>9. Other companies' services</h2>
<p>Payvoro uses services from other companies, such as Google (login) and Razorpay (subscription payments).
Their own terms apply to their services. Payvoro is an independent product. It is <b>not</b> made by, partnered with,
or endorsed by Razorpay, Google, NPCI, any bank or any UPI app. Names like GPay, PhonePe, Paytm and BHIM belong
to their owners and are used only to say which apps Payvoro can read alerts from.</p>

<h2>10. No warranty</h2>
<p>Payvoro is provided "as is" and "as available". We work hard to keep it running, but we do not promise that
it will be error-free or available all the time.</p>

<h2>11. Limit of our liability</h2>
<p>To the extent the law allows, we are not liable for indirect or consequential losses (such as lost profit or
lost sales). Our total liability for any claim is limited to the subscription fee you paid us for the
<b>one month</b> before the claim.</p>

<h2>12. Suspension and ending</h2>
<ul>
<li>You can stop using Payvoro and ask us to delete your account at any time.</li>
<li>We may suspend or close an account that breaks these Terms, is used for fraud, or when the law or our
payment partner requires it. Where possible, we will tell you first and explain why.</li>
</ul>

<h2>13. Changes to these Terms</h2>
<p>We may update these Terms. We will show the new date at the bottom of this page and, for important changes,
tell you in the app. Using Payvoro after a change means you accept the new Terms.</p>

<h2>14. Law and courts</h2>
<p>These Terms are governed by the laws of India. Courts at <b>{d['city']}</b> have jurisdiction.</p>

<h2>15. Contact and grievances</h2>
<p>For questions or complaints, contact us. We reply within 2 business days and try to resolve complaints within
4 business days.</p>
{_contact_block(d)}
"""
    return _page("Terms of Service", body)


def privacy_html() -> str:
    d = details()
    body = f"""
<p>This Privacy Policy explains what data <b>{d['name']}</b> ("Payvoro", "we") collects through the Payvoro app
and website, why, and your choices. It follows India's Digital Personal Data Protection Act, 2023 and the
Information Technology Act, 2000.</p>

<div class="box"><b>Short version.</b> Your customers' payments stay on your phone. We store only what we need for
your account and subscription. We never sell your data.</div>

<h2>1. Data we store on our server</h2>
<ul>
<li><b>Google account:</b> your name, email address and Google account ID (to log you in).</li>
<li><b>Shop details:</b> shop name, UPI ID, city, and phone number if you give it.</li>
<li><b>Subscription:</b> plan, trial and end dates, AutoPay status, and Razorpay subscription/payment reference IDs.</li>
<li><b>Device:</b> phone maker and model, and the last time the app contacted our server.</li>
</ul>

<h2>2. Data that stays only on your phone</h2>
<ul>
<li>Payvoro needs <b>notification access</b> to hear payment alerts. It looks only at notifications from the UPI
and bank SMS apps you allow in the app. All other notifications are ignored and not saved.</li>
<li>From a payment alert, Payvoro keeps the amount, the payer name shown, the app name, the time and the reference
number in your phone's own storage, to show your payment history for 30 days.</li>
<li>This payment data is <b>not sent to our server</b> and we cannot see it.</li>
</ul>

<h2>3. Subscription payments</h2>
<p>Your monthly fee is processed by Razorpay. You enter your UPI or bank details on Razorpay's page or in your UPI
app, not in Payvoro. We never see or store your UPI PIN, card number, CVV or bank login.
Razorpay handles that data under its own privacy policy.</p>

<h2>4. Why we use your data</h2>
<ul>
<li>To log you in and run your account.</li>
<li>To start, renew and manage your subscription, and to answer support requests.</li>
<li>To keep the service secure and prevent fraud or misuse.</li>
<li>To meet legal, tax and accounting duties.</li>
</ul>

<h2>5. Who we share it with</h2>
<p>We share data only with service providers who help us run Payvoro, and only what they need:</p>
<ul>
<li><b>Razorpay</b>: subscription payments (your email and subscription details).</li>
<li><b>Google</b>: login.</li>
<li><b>Hosting</b>: our server and database providers (for example Vercel and Neon). The servers may be outside India.</li>
<li><b>Government or courts</b>, when Indian law requires it.</li>
</ul>
<p>We do not sell or rent your personal data, and we do not use it for advertising.</p>

<h2>6. How long we keep it</h2>
<p>We keep your account data while your account is active. If you ask us to delete your account, we delete your
personal data within 30 days, except records we must keep by law (for example, billing records for tax purposes).
Payment history on your phone is deleted when you uninstall the app or clear its data.</p>

<h2>7. Security</h2>
<p>We use HTTPS for all traffic, keep server access limited, and store only the data listed above.
No system is perfectly secure; if we learn of a data breach that affects you, we will tell you and the authorities
as the law requires.</p>

<h2>8. Your rights</h2>
<p>You can ask us to: show what data we hold about you; correct it; delete it; or withdraw your consent
(this will end your account, since we need some data to provide the service). You can also turn off notification
access in your phone settings at any time; Payvoro will then stop announcing payments.</p>

<h2>9. Children</h2>
<p>Payvoro is for businesses and is not meant for anyone under 18.</p>

<h2>10. Changes</h2>
<p>We may update this policy and will show the new date below. For important changes we will tell you in the app.</p>

<h2>11. Grievance officer and contact</h2>
<p>For privacy questions or complaints, contact our grievance officer. We reply within 2 business days.</p>
{_contact_block(d)}
"""
    return _page("Privacy Policy", body)


def refund_html(price: int, per_day: str, trial_days: int) -> str:
    d = details()
    body = f"""
<p>This policy explains how to cancel your Payvoro subscription and when you can get a refund.
It is part of our <a href="/terms">Terms of Service</a>.</p>

<h2>1. Plan and billing</h2>
<ul>
<li>Plan: <b>Basic</b>, <b>₹{price} per month</b> (shown as ₹{per_day} per day), collected by UPI AutoPay through Razorpay.</li>
<li>Your first plan starts with a <b>{trial_days}-day free trial</b>. No money is taken during the trial.</li>
<li>After the trial, ₹{price} is charged once a month on the same date until you cancel.</li>
</ul>

<h2>2. How to cancel</h2>
<ul>
<li><b>In your UPI app:</b> open the AutoPay / Mandates section and cancel the Payvoro (Razorpay) mandate. Or</li>
<li><b>Contact us</b> by email or phone (details below) and we will cancel it for you.</li>
</ul>
<p>After you cancel, no more money is taken. Your plan keeps working until the end of the month you already paid for.
If you cancel during the free trial, you are never charged.</p>

<h2>3. Refunds</h2>
<p>A month that has already started is normally not refunded. But we <b>will give a full refund</b> of that month's fee if:</p>
<ul>
<li>you were charged more than once for the same month, or charged the wrong amount;</li>
<li>you were charged after your cancellation was confirmed; or</li>
<li>Payvoro did not work for most of that month because of a problem on our side that we could not fix.</li>
</ul>
<p>Please ask for a refund within <b>7 days</b> of the charge, by email or phone, with your registered email and the
date of the charge.</p>

<h2>4. Refund timeline</h2>
<ul>
<li>We reply to a refund request within 2 business days.</li>
<li>Approved refunds are sent back to the <b>same payment method</b> you paid with (your UPI / bank account),
usually within 5–7 business days. Your bank may take a little longer to show it.</li>
<li>If money was deducted from your account but the payment failed, it is reversed automatically by your bank
under RBI timelines. If it is not, contact us and we will help.</li>
</ul>

<h2>5. Contact</h2>
{_contact_block(d)}
"""
    return _page("Refund & Cancellation Policy", body)


def contact_html() -> str:
    d = details()
    body = f"""
<p>Need help with Payvoro, a subscription charge, or a refund? Contact us. We reply within 2 business days and try
to resolve complaints within 4 business days.</p>
{_contact_block(d)}
<h2>Grievance officer</h2>
<p>For complaints about the service or about your personal data, write to our grievance officer,
<b>{d['officer']}</b>, at {d['email']}. Please include your registered email and a short description of the issue.</p>
"""
    return _page("Contact & Grievance", body)
