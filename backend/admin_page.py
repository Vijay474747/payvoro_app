"""HTML for the home page (/). The admin dashboard (/admin) is in admin_html.py."""

from admin_html import ADMIN_HTML  # noqa: E402,F401  (the admin page lives in admin_html.py since v4.2)


HOME_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Payvoro Sound Box</title>
<meta name="description" content="Turn any Android phone into a UPI sound box. Voice alerts in Tamil and English.">
<style>
:root{--brand:#5b3fe8;--brand-d:#3a22b8;--ink:#16141f;--mute:#6b6880;--bg:#f6f5fb}
*{box-sizing:border-box}body{margin:0;font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg)}
.hero{background:linear-gradient(160deg,var(--brand-d),var(--brand));color:#fff;padding:56px 16px 90px;text-align:center}
.hero h1{font-size:clamp(30px,6vw,46px);margin:0 0 10px;line-height:1.1}.hero p{opacity:.9;max-width:560px;margin:0 auto;font-size:18px}
.say{display:inline-block;margin-top:22px;background:#ffffff1f;border:1px solid #ffffff40;border-radius:14px;padding:12px 18px;font-size:20px;font-weight:700}
.wrap{max-width:900px;margin:-56px auto 0;padding:0 16px 48px}
.plans{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}
.plan{background:#fff;border-radius:18px;padding:22px;border:1px solid #ebe9f3;box-shadow:0 8px 24px #3a22b81a}
.plan h2{margin:0;font-size:20px}.price{font-size:40px;font-weight:800;color:var(--brand-d);margin:6px 0 0}.price small{font-size:16px;color:var(--mute)}
.month{color:var(--mute);font-size:14px;margin-bottom:12px}ul{padding-left:20px;margin:0}li{margin:4px 0}
.steps{margin-top:28px;background:#fff;border-radius:18px;padding:22px;border:1px solid #ebe9f3}.steps h2{margin-top:0;font-size:20px}
footer{text-align:center;color:var(--mute);font-size:13px;padding:20px}footer a{color:var(--mute)}
</style></head><body>
<section class="hero"><h1>Payvoro Sound Box</h1><p>Turn any Android phone into a UPI sound box. No hardware. Keep your own shop QR.</p>
<div class="say">🔊 “500 ரூபாய் பெறப்பட்டது”</div></section>
<div class="wrap"><div class="plans" id="plans"></div>
<div class="steps"><h2>How it works</h2><ol><li>Install the Payvoro app and log in with Google.</li><li>Scan your shop's UPI QR sticker.</li>
<li>Pick a plan and approve UPI AutoPay. The first days are free.</li><li>Every GPay, PhonePe, Paytm or BHIM payment is announced aloud.</li></ol></div></div>
<p style="max-width:900px;margin:0 auto;padding:0 16px;color:var(--mute);font-size:13px;text-align:center">Payvoro only reads payment
notifications on your own phone and speaks the amount. It does not receive, hold or verify any money: customers pay you directly
through your own UPI ID. Payvoro is not affiliated with Razorpay, Google, NPCI or any UPI app.</p>
<footer><a href="/terms">Terms</a> · <a href="/privacy">Privacy</a> · <a href="/refund">Refund &amp; Cancellation</a> ·
<a href="/contact">Contact</a> · <a href="/admin">Admin</a></footer>
<script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
fetch('/api/plans').then(r=>r.json()).then(d=>{document.getElementById('plans').innerHTML=d.plans.map(p=>`<div class="plan"><h2>${esc(p.name)}</h2>
<div class="price">₹${esc(p.per_day)}<small>/day</small></div><div class="month">₹${esc(p.price)} per month by UPI AutoPay · ${d.trial_days} days free</div>
<ul>${p.features.map(f=>`<li>${esc(f)}</li>`).join('')}</ul></div>`).join('')}).catch(()=>{});
</script></body></html>"""
