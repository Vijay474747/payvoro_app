"""Admin dashboard page (/admin). Plain HTML + JS, no build step. Talks to the /admin/* API in main.py.

v4.3 design: dark dashboard with a side menu. Only four pages: Home (money + charts), Shops (simple list,
click a shop for its detail panel), AutoPay (automatic Razorpay check, unmatched AutoPays, pay-by-link
approvals) and Setup. No plan dropdown and no "+1 month": a plan changes only by Razorpay AutoPay
(checked automatically) or by free days with a written reason.
"""

ADMIN_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Payvoro Admin</title>
<meta name="robots" content="noindex"><meta name="theme-color" content="#0b0d14">
<style>
:root{--bg:#0b0d14;--side:#0f121b;--panel:#131722;--panel2:#181d2a;--line:#232838;--ink:#e8eaf2;--mute:#8b91a7;--dim:#5d6378;
 --green:#22e58b;--green-d:#0f3d2a;--purple:#8b5cf6;--purple-d:#2a1f4d;--red:#ff4d6d;--red-d:#3d1520;--amber:#ffb020;--amber-d:#3d2e0d;--blue:#38bdf8}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 "Inter",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--purple)}button{font:inherit;cursor:pointer;border:0;border-radius:10px;padding:9px 14px;font-weight:600;color:#0b0d14;background:var(--green)}
button:hover{filter:brightness(1.1)}button:disabled{opacity:.45;cursor:default}
button.sec{background:var(--panel2);color:var(--ink);border:1px solid var(--line)}button.danger{background:var(--red-d);color:var(--red);border:1px solid #5a2030}
button.pur{background:var(--purple);color:#fff}button.sm{padding:6px 10px;font-size:12px;border-radius:8px}
input,select{font:inherit;color:var(--ink);background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:9px 12px;min-width:0}
input:focus,select:focus{outline:2px solid var(--purple);outline-offset:-1px}input::placeholder{color:var(--dim)}
.hidden{display:none!important}
/* layout */
.shell{display:flex;min-height:100vh}
aside{width:228px;flex:none;background:var(--side);border-right:1px solid var(--line);padding:22px 14px;position:sticky;top:0;height:100vh;display:flex;flex-direction:column}
.logo{display:flex;align-items:center;gap:10px;font-weight:800;font-size:18px;padding:0 8px 26px}
.logo i{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,var(--purple),var(--green));display:grid;place-items:center;font-style:normal;color:#fff}
.nav a{display:flex;align-items:center;gap:12px;padding:11px 12px;border-radius:12px;color:var(--mute);text-decoration:none;font-weight:600;cursor:pointer;margin-bottom:4px;position:relative}
.nav a svg{width:19px;height:19px;flex:none}.nav a:hover{color:var(--ink);background:var(--panel)}
.nav a.on{color:var(--ink);background:linear-gradient(90deg,var(--purple-d),transparent);box-shadow:inset 3px 0 0 var(--purple)}
.nav a .cnt{margin-left:auto;background:var(--red);color:#fff;font-size:11px;border-radius:999px;padding:0 7px;line-height:18px}
aside .foot{margin-top:auto;color:var(--dim);font-size:12px;padding:0 8px}aside .foot a{color:var(--mute);cursor:pointer}
main{flex:1;min-width:0;padding:22px 28px 60px}
.top{display:flex;align-items:center;gap:10px;margin-bottom:22px;flex-wrap:wrap}.top h1{font-size:22px;margin:0;flex:1}
.top .sub{color:var(--mute);font-size:13px;width:100%;margin-top:-6px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;min-width:0}
.panel h2{font-size:15px;margin:0 0 2px}.panel .hint{color:var(--mute);font-size:12.5px;margin:0 0 14px}
.grid{display:grid;gap:16px}.stats{grid-template-columns:repeat(4,minmax(0,1fr))}.two{grid-template-columns:1.4fr 1fr}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;position:relative;overflow:hidden;cursor:pointer}
.stat:hover{border-color:#343a50}.stat small{color:var(--mute);font-weight:600;font-size:12.5px}
.stat b{display:block;font-size:30px;margin:6px 0 2px;font-variant-numeric:tabular-nums;letter-spacing:-.5px}.stat em{font-style:normal;color:var(--dim);font-size:12px}
.stat::after{content:"";position:absolute;right:-30px;top:-30px;width:110px;height:110px;border-radius:50%;background:var(--glow);opacity:.18;filter:blur(8px)}
.stat .ic{position:absolute;right:16px;top:16px;width:34px;height:34px;border-radius:10px;display:grid;place-items:center;background:var(--tint);color:var(--glow)}
.stat .ic svg{width:18px;height:18px}
.banner{border-radius:12px;padding:12px 14px;margin-bottom:16px;font-weight:600;background:var(--amber-d);color:var(--amber);border:1px solid #5a4410}
.banner.red{background:var(--red-d);color:var(--red);border-color:#5a2030}
/* charts */
.chart svg{width:100%;height:190px;display:block}.chart .cap{display:flex;justify-content:space-between;color:var(--dim);font-size:11px;margin-top:6px}
.big{font-size:26px;font-weight:800;letter-spacing:-.5px}.big small{font-size:13px;color:var(--mute);font-weight:500;margin-left:6px}
/* lists */
.att{display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--line);cursor:pointer}.att:last-child{border:0}
.att .n{min-width:36px;height:36px;border-radius:10px;display:grid;place-items:center;font-weight:800}
.att span{flex:1;color:var(--mute)}.att:hover span{color:var(--ink)}
.toolbar{display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap}.toolbar input{flex:1;min-width:180px}
table{width:100%;border-collapse:collapse}th{color:var(--dim);font-size:11.5px;text-transform:uppercase;letter-spacing:.5px;font-weight:600;text-align:left;padding:0 12px 10px}
td{padding:12px;border-top:1px solid var(--line);vertical-align:middle}tbody tr{cursor:pointer}tbody tr:hover td{background:var(--panel2)}
.shop{display:flex;align-items:center;gap:12px;min-width:0}.av{width:38px;height:38px;border-radius:12px;flex:none;display:grid;place-items:center;font-weight:800;color:#fff}
.shop b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:260px}.shop small{color:var(--dim);display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:260px}
.pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:3px 10px;font-size:12px;font-weight:700;white-space:nowrap}
.p-basic{background:var(--purple-d);color:#c4b5fd}.p-trial{background:var(--amber-d);color:var(--amber)}.p-expired{background:var(--red-d);color:var(--red)}
.p-no_plan{background:#1d2130;color:var(--mute)}.p-stopped{background:#1d2130;color:var(--dim);text-decoration:line-through}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;flex:none}.ap{display:flex;align-items:center;gap:8px;white-space:nowrap;font-weight:600}
.ok{color:var(--green)}.bad{color:var(--red)}.warn{color:var(--amber)}.mute{color:var(--mute)}.dim{color:var(--dim)}
.empty{color:var(--dim);text-align:center;padding:26px}
/* drawer */
.veil{position:fixed;inset:0;background:#0009;z-index:20;opacity:0;pointer-events:none;transition:opacity .2s}.veil.on{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;right:0;height:100%;width:min(520px,100%);background:var(--side);border-left:1px solid var(--line);z-index:21;
 transform:translateX(100%);transition:transform .25s ease;overflow-y:auto;padding:22px}.drawer.on{transform:none}
.dhead{display:flex;align-items:center;gap:14px;margin-bottom:18px}.dhead .av{width:52px;height:52px;font-size:20px;border-radius:16px}
.dhead h2{margin:0;font-size:19px}.dhead .x{margin-left:auto;background:var(--panel2);color:var(--ink);width:38px;height:38px;padding:0;border-radius:12px;font-size:18px}
.facts{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px}.fact{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:11px 13px;min-width:0}
.fact small{color:var(--dim);font-size:11.5px;display:block}.fact b{display:block;margin-top:2px;overflow-wrap:anywhere;font-size:14px}
.sec-t{font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:var(--dim);font-weight:700;margin:22px 0 10px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.row>.grow{flex:1;min-width:120px}
.li{display:flex;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line);font-size:13px}.li:last-child{border:0}.li .grow{flex:1;min-width:0}
.ck{display:flex;gap:12px;align-items:flex-start;padding:12px 0;border-bottom:1px solid var(--line)}.ck:last-child{border:0}
.ck .i{width:24px;height:24px;border-radius:8px;display:grid;place-items:center;font-weight:800;font-size:13px;flex:none}
.i.y{background:var(--green-d);color:var(--green)}.i.n{background:var(--red-d);color:var(--red)}.i.w{background:var(--amber-d);color:var(--amber)}
code{background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:1px 6px;font-size:12px;overflow-wrap:anywhere}
#login{max-width:380px;margin:14vh auto;padding:28px}#login input{width:100%;margin:14px 0}#login button{width:100%}
#toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:11px 18px;border-radius:12px;font-weight:600;
 display:none;z-index:40;max-width:90vw}
dialog{background:var(--side);color:var(--ink);border:1px solid var(--line);border-radius:16px;padding:22px;width:min(440px,94vw)}dialog::backdrop{background:#000a}
dialog input{width:100%;margin-bottom:10px}
@media(max-width:1100px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.two{grid-template-columns:1fr}}
@media(max-width:760px){
 aside{position:fixed;bottom:0;top:auto;left:0;right:0;width:auto;height:auto;flex-direction:row;padding:6px 8px;z-index:15;border-right:0;border-top:1px solid var(--line)}
 .logo,aside .foot{display:none}.nav{display:flex;width:100%}.nav a{flex:1;flex-direction:column;gap:2px;font-size:11px;padding:8px 4px;margin:0;justify-content:center}
 .nav a.on{box-shadow:inset 0 3px 0 var(--purple);background:var(--panel)}.nav a .cnt{position:absolute;top:2px;right:18%;margin:0}
 main{padding:16px 16px 90px}.stat b{font-size:24px}
 thead{display:none}tbody tr{display:grid;grid-template-columns:1fr auto;gap:6px 10px;padding:12px;border-top:1px solid var(--line)}
 tbody td{border:0;padding:0}td.c-plan,td.c-until{grid-column:1}td.c-ap{grid-column:1}td.c-seen{display:none}td.c-act{grid-row:1;grid-column:2}
 .shop b,.shop small{max-width:200px}}
</style></head><body>
<div id="login" class="panel"><div class="logo" style="padding:0 0 10px"><i>▶</i>Payvoro Admin</div>
 <p class="mute" style="margin:0">Enter your admin key (PAYVORO_ADMIN_KEY).</p>
 <input id="key" type="password" placeholder="Admin key" autocomplete="current-password"><button id="loginBtn">Log in</button></div>

<div class="shell hidden" id="shell">
 <aside><div class="logo"><i>▶</i>Payvoro</div>
  <nav class="nav" id="nav">
   <a data-p="home" class="on"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/></svg>Home</a>
   <a data-p="shops"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 9l1-5h14l1 5M4 9v11h16V9M4 9h16M9 20v-6h6v6"/></svg>Shops</a>
   <a data-p="autopay"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M7 15h4"/></svg>AutoPay<span class="cnt hidden" id="apCnt"></span></a>
   <a data-p="setup"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>Setup</a>
  </nav>
  <div class="foot">Updated <span id="upd">—</span><br><a id="logout">Log out</a></div>
 </aside>

 <main>
  <div id="banners"></div>

  <!-- HOME -->
  <section data-page="home">
   <div class="top"><h1>Dashboard</h1><button class="sec" onclick="load(true)">↻ Refresh</button></div>
   <div class="grid stats" id="stats"></div>
   <div class="grid two" style="margin-top:16px">
    <div class="panel"><div class="row"><div class="grow"><h2>Income</h2><p class="hint">Money received from shops – last 6 months</p></div>
     <div class="big" id="incomeNow"></div></div><div class="chart" id="incomeChart"></div></div>
    <div class="panel"><h2>Needs attention</h2><p class="hint">Tap to open</p><div id="attention"></div></div>
   </div>
   <div class="grid two" style="margin-top:16px">
    <div class="panel"><div class="row"><div class="grow"><h2>New shops</h2><p class="hint">Sign-ups – last 30 days</p></div><div class="big" id="newNow"></div></div>
     <div class="chart" id="signupChart"></div></div>
    <div class="panel"><h2>Plans</h2><p class="hint">All shops by plan</p><div id="donut"></div></div>
   </div>
  </section>

  <!-- SHOPS -->
  <section data-page="shops" class="hidden">
   <div class="top"><h1>Shops <span class="dim" id="count" style="font-size:15px;font-weight:500"></span></h1>
    <button class="sec" onclick="addDlg.showModal()">+ Add shop</button></div>
   <div class="panel">
    <div class="toolbar"><input id="q" placeholder="Search shop name, email, phone or UPI ID">
     <select id="flt"><option value="all">All shops</option><option value="basic">Paying (Basic)</option><option value="trial">Free trial</option>
      <option value="expired">Expired</option><option value="no_plan">No plan</option><option value="stopped">Stopped</option>
      <option value="ap_failed">AutoPay failed</option><option value="ending">Ending in 3 days</option></select></div>
    <div style="overflow-x:auto"><table><thead><tr><th>Shop</th><th>Plan</th><th>AutoPay</th><th>Plan until</th><th>Last seen</th><th></th></tr></thead>
     <tbody id="rows"></tbody></table></div>
   </div>
  </section>

  <!-- AUTOPAY -->
  <section data-page="autopay" class="hidden">
   <div class="top"><h1>AutoPay</h1><button id="syncBtn" onclick="syncAll(this)">⟳ Check with Razorpay</button>
    <div class="sub">AutoPay is verified automatically: by the webhook, when the shop opens the app, and every night at 2 AM.</div></div>
   <div id="syncInfo"></div>
   <div class="panel" style="margin-top:16px"><h2>AutoPays with no shop</h2>
    <p class="hint">Found in Razorpay, but the email / mobile / UPI ID matched no shop. Pick the shop once.</p><div id="unmatched"></div></div>
   <div class="panel" style="margin-top:16px"><h2>Pay-by-link waiting</h2>
    <p class="hint">Shops that paid one month on your razorpay.me page. Check Razorpay, then approve (+30 days).</p><div id="pending"></div></div>
  </section>

  <!-- SETUP -->
  <section data-page="setup" class="hidden">
   <div class="top"><h1>Setup</h1></div>
   <div class="grid two"><div class="panel"><h2>Server checklist</h2><p class="hint">Everything green before going live</p><div id="setup"></div></div>
    <div class="panel"><h2>Plan</h2><p class="hint">Fixed in backend/core.py (PLANS)</p><div id="plan"></div></div></div>
  </section>
 </main>
</div>

<div class="veil" id="veil" onclick="closeShop()"></div>
<div class="drawer" id="drawer" aria-label="Shop details"></div>

<dialog id="addDlg"><h2 style="margin:0 0 4px">Add shop</h2><p class="mute" style="margin:0 0 14px;font-size:13px">The owner then logs in to the app with this Google account.</p>
 <input id="n" placeholder="Shop name"><input id="e" placeholder="Google email"><input id="p" placeholder="Phone (optional)">
 <input id="u" placeholder="UPI ID (optional)"><div class="row"><button class="sec grow" onclick="addDlg.close()">Cancel</button><button class="grow" id="addBtn">Add shop</button></div></dialog>
<div id="toast"></div>

<script>
const $=id=>document.getElementById(id);
const store={get(k){try{return localStorage.getItem(k)||''}catch(e){return ''}},set(k,v){try{v?localStorage.setItem(k,v):localStorage.removeItem(k)}catch(e){}}};
let K=store.get('pvk'),D=null,page=store.get('pvpage')||'home',S=null,edit=false;
const LABEL={basic:'Basic',trial:'Free trial',expired:'Expired',no_plan:'No plan',stopped:'Stopped'};
const PCOL={basic:'#8b5cf6',trial:'#ffb020',expired:'#ff4d6d',no_plan:'#5d6378',stopped:'#343a50'};
const AV=['#8b5cf6','#22c55e','#0ea5e9','#f59e0b','#ec4899','#14b8a6','#6366f1'];
const rs=n=>'₹'+Number(n||0).toLocaleString('en-IN',{maximumFractionDigits:0});
const dd=t=>t?new Date(Number(t)).toLocaleDateString('en-IN',{day:'numeric',month:'short',year:'numeric'}):'—';
const dt=t=>t?new Date(Number(t)).toLocaleString('en-IN',{day:'numeric',month:'short',hour:'numeric',minute:'2-digit'}):'—';
const ago=t=>{if(!t)return 'never';const s=(Date.now()-t)/1000;if(s<60)return 'just now';if(s<3600)return Math.floor(s/60)+' min ago';if(s<86400)return Math.floor(s/3600)+' h ago';return Math.floor(s/86400)+' d ago'};
const left=t=>{const d=Math.ceil((t-Date.now())/86400000);return d>1?d+' days left':d===1?'1 day left':d===0?'ends today':'ended'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const av=m=>`<div class="av" style="background:${AV[m.id%AV.length]}">${esc((m.name||m.email||'?').trim().charAt(0).toUpperCase())}</div>`;
function toast(m){const t=$('toast');t.textContent=m;t.style.display='block';clearTimeout(t._h);t._h=setTimeout(()=>t.style.display='none',3500)}
async function api(path,opt={}){opt.headers={'X-Admin-Key':K,'Content-Type':'application/json'};
 const r=await fetch(path,opt);const j=await r.json().catch(()=>({}));
 if(r.status===401){logoutUI('Wrong admin key');throw new Error('401')}
 if(!r.ok){const d=j.detail;toast(typeof d==='string'?d:(Array.isArray(d)&&d[0]?.msg)||('Error '+r.status));throw new Error(r.status)}return j}
const post=(p,b)=>api(p,{method:'POST',body:JSON.stringify(b||{})});
function busy(b,on){if(!b)return;b.disabled=on;if(on){b._t=b.innerHTML;b.innerHTML='Working…'}else if(b._t)b.innerHTML=b._t}
function logoutUI(msg){$('login').classList.remove('hidden');$('shell').classList.add('hidden');closeShop();if(msg)toast(msg)}
$('loginBtn').onclick=()=>{K=$('key').value.trim();store.set('pvk',K);load()};
$('key').onkeydown=e=>{if(e.key==='Enter')$('loginBtn').onclick()};
$('logout').onclick=()=>{K='';store.set('pvk','');$('key').value='';logoutUI()};
document.querySelectorAll('#nav a').forEach(a=>a.onclick=()=>go(a.dataset.p));
$('q').oninput=renderShops;$('flt').onchange=renderShops;
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeShop()});
function go(p,f){page=p;store.set('pvpage',p);document.querySelectorAll('#nav a').forEach(a=>a.classList.toggle('on',a.dataset.p===p));
 document.querySelectorAll('section[data-page]').forEach(s=>s.classList.toggle('hidden',s.dataset.page!==p));
 if(f){$('flt').value=f;$('q').value='';renderShops()}window.scrollTo({top:0})}

async function load(manual){if(!K){logoutUI();return}
 D=await api('/admin/dashboard');const first=$('shell').classList.contains('hidden');
 $('login').classList.add('hidden');$('shell').classList.remove('hidden');$('upd').textContent=new Date().toLocaleTimeString('en-IN',{hour:'numeric',minute:'2-digit'});
 renderAll();if(first)go(page);if(manual)toast('Updated')}

function renderAll(){const s=D.stats,st=s.setup;let b='';
 if(!st.database_ok)b+='<div class="banner red">No database connected on Vercel – data will be lost. Add Neon Postgres, then redeploy.</div>';
 if(st.dev_mode)b+='<div class="banner red">Test mode (PAYVORO_DEV=1) is on – anyone can log in. Turn it off on the live server.</div>';
 if(!st.razorpay_keys)b+='<div class="banner">Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET on Vercel so AutoPay is checked with Razorpay automatically.</div>';
 if(st.legal_missing&&st.legal_missing.length)b+=`<div class="banner">Policy pages need your contact details: ${st.legal_missing.map(esc).join(', ')} (Vercel settings).</div>`;
 $('banners').innerHTML=b;
 const failed=s.autopay_failed||0,need=failed+(s.ending_soon||0)+D.unmatched.length+D.pending.length;
 const I={money:'<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',shop:'<path d="M4 9l1-5h14l1 5M4 9v11h16V9M4 9h16"/>',
  card:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18"/>',alert:'<path d="M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'};
 const card=(label,val,sub,col,tint,icon,act)=>`<div class="stat" style="--glow:${col};--tint:${tint}" onclick="${act}"><span class="ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${I[icon]}</svg></span>
  <small>${label}</small><b>${val}</b><em>${sub}</em></div>`;
 $('stats').innerHTML=card('Monthly income',rs(s.monthly_income),s.paying+' paying shops','var(--green)','var(--green-d)','money',"go('shops','basic')")+
  card('Total shops',s.total_users,'+'+s.new_7_days+' this week','var(--purple)','var(--purple-d)','shop',"go('shops','all')")+
  card('AutoPay on',s.autopay_on,'verified with Razorpay','var(--blue)','#0c2a3a','card',"go('autopay')")+
  card('Needs attention',need,need?'tap to see':'all good','var(--red)','var(--red-d)','alert',"document.getElementById('attention').scrollIntoView({behavior:'smooth'})");
 const inc=D.charts.income;$('incomeNow').innerHTML=rs(inc[inc.length-1]?.value)+'<small>this month</small>';
 bars('incomeChart',inc,rs);
 const sg=D.charts.signups;$('newNow').innerHTML=sg.reduce((a,x)=>a+x.value,0)+'<small>in 30 days</small>';area('signupChart',sg);
 donut();
 const A=[[failed,'AutoPay charge failed – call the shop','var(--red)','var(--red-d)',"go('shops','ap_failed')"],
  [s.ending_soon,'Plan ends in 3 days, no AutoPay','var(--amber)','var(--amber-d)',"go('shops','ending')"],
  [D.unmatched.length,'AutoPay in Razorpay with no shop','var(--purple)','var(--purple-d)',"go('autopay')"],
  [D.pending.length,'Pay-by-link waiting for approval','var(--blue)','#0c2a3a',"go('autopay')"],
  [s.by_status.expired,'Expired plans','var(--mute)','#1d2130',"go('shops','expired')"]].filter(a=>a[0]>0);
 $('attention').innerHTML=A.length?A.map(a=>`<div class="att" onclick="${a[4]}"><div class="n" style="color:${a[2]};background:${a[3]}">${a[0]}</div><span>${a[1]}</span><span class="dim" style="flex:none">›</span></div>`).join('')
  :'<div class="empty"><div class="ok" style="font-size:28px">✓</div>Nothing needs you right now</div>';
 const ac=D.unmatched.length+D.pending.length;$('apCnt').textContent=ac;$('apCnt').classList.toggle('hidden',!ac);
 renderShops();renderAutopay();renderSetup();if(S&&$('drawer').classList.contains('on'))openShop(S.merchant.id,true)}

function bars(id,data,fmt){const W=600,H=190,max=Math.max(1,...data.map(d=>d.value)),w=W/data.length;
 $(id).innerHTML=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><defs><linearGradient id="gb" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#22e58b"/><stop offset="1" stop-color="#8b5cf6"/></linearGradient></defs>
 ${[0,1,2,3].map(i=>`<line x1="0" x2="${W}" y1="${10+i*55}" y2="${10+i*55}" stroke="#232838" stroke-dasharray="3 5"/>`).join('')}
 ${data.map((d,i)=>{const h=d.value/max*165;return `<rect x="${i*w+w*.22}" y="${175-h}" width="${w*.56}" height="${Math.max(h,2)}" rx="7" fill="${d.value?'url(#gb)':'#232838'}"><title>${esc(d.label)}: ${fmt(d.value)}</title></rect>`}).join('')}</svg>
 <div class="cap">${data.map(d=>`<span>${esc(d.label.split(' ')[0])}</span>`).join('')}</div>`}
function area(id,data){const W=600,H=190,max=Math.max(1,...data.map(d=>d.value)),n=data.length-1;
 const pts=data.map((d,i)=>[i/n*W,175-d.value/max*160]);const line=pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
 $(id).innerHTML=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><defs><linearGradient id="ga" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8b5cf6" stop-opacity=".55"/><stop offset="1" stop-color="#8b5cf6" stop-opacity="0"/></linearGradient></defs>
 ${[0,1,2,3].map(i=>`<line x1="0" x2="${W}" y1="${10+i*55}" y2="${10+i*55}" stroke="#232838" stroke-dasharray="3 5"/>`).join('')}
 <path d="${line} L${W} 178 L0 178Z" fill="url(#ga)"/><path d="${line}" fill="none" stroke="#a78bfa" stroke-width="3" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
 ${data.map((d,i)=>d.value?`<circle cx="${pts[i][0]}" cy="${pts[i][1]}" r="4" fill="#22e58b"><title>${esc(d.label)}: ${d.value}</title></circle>`:'').join('')}</svg>
 <div class="cap"><span>${esc(data[0].label)}</span><span>${esc(data[15].label)}</span><span>${esc(data[n].label)}</span></div>`}
function donut(){const by=D.stats.by_status,tot=Math.max(1,D.stats.total_users),keys=Object.keys(LABEL);let a=0;
 const R=60,C=2*Math.PI*R;const segs=keys.map(k=>{const v=by[k]||0,len=v/tot*C,s=`<circle r="${R}" cx="80" cy="80" fill="none" stroke="${PCOL[k]}" stroke-width="20" stroke-dasharray="${len} ${C-len}" stroke-dashoffset="${-a}" transform="rotate(-90 80 80)"/>`;a+=len;return v?s:''}).join('');
 $('donut').innerHTML=`<div class="row" style="gap:22px;flex-wrap:nowrap"><svg viewBox="0 0 160 160" width="150" height="150" style="flex:none"><circle r="${R}" cx="80" cy="80" fill="none" stroke="#232838" stroke-width="20"/>${segs}
 <text x="80" y="78" text-anchor="middle" fill="#e8eaf2" font-size="26" font-weight="800">${D.stats.total_users}</text><text x="80" y="98" text-anchor="middle" fill="#8b91a7" font-size="11">shops</text></svg>
 <div class="grow">${keys.map(k=>`<div class="li" style="cursor:pointer;padding:7px 0" onclick="go('shops','${k}')"><span class="dot" style="background:${PCOL[k]}"></span><span class="grow">${LABEL[k]}</span><b>${by[k]||0}</b></div>`).join('')}</div></div>`}

// ---------- shops ----------
const apText=m=>{const s=m.autopay_status;
 if(s==='active')return ['var(--green)','Active'];if(s==='authenticated')return ['var(--green)','Set · trial'];
 if(s==='pending'||s==='halted')return ['var(--red)','Failed'];if(s==='cancelled')return ['var(--dim)','Cancelled'];return ['#343a50','Not set']};
function renderShops(){const q=$('q').value.trim().toLowerCase(),f=$('flt').value;
 const list=D.merchants.filter(m=>(f==='all'||m.status===f||(f==='ap_failed'&&['pending','halted'].includes(m.autopay_status))||(f==='ending'&&m.ending_soon))
  &&(!q||[m.name,m.email,m.phone,m.upi_id,m.city].some(v=>String(v||'').toLowerCase().includes(q))));
 $('count').textContent=list.length+' of '+D.merchants.length;
 $('rows').innerHTML=list.length?list.map(m=>{const [c,t]=apText(m);return `<tr onclick="openShop(${m.id})">
  <td><div class="shop">${av(m)}<div style="min-width:0"><b>${esc(m.name)||'<i class="dim">No shop name</i>'}</b><small>${esc(m.email)}</small></div></div></td>
  <td class="c-plan"><span class="pill p-${m.status}">${LABEL[m.status]}</span></td>
  <td class="c-ap"><span class="ap"><span class="dot" style="background:${c}"></span>${t}</span></td>
  <td class="c-until">${m.plan_until?`<span class="${m.plan_active?(m.ending_soon?'warn':''):'bad'}">${dd(m.plan_until)}</span>`:'<span class="dim">—</span>'}</td>
  <td class="c-seen ${m.online?'ok':'mute'}">${m.online?'● Online':ago(m.last_seen)}</td>
  <td class="c-act" style="text-align:right"><button class="sm ${m.active?'danger':''}" onclick="event.stopPropagation();tog(${m.id},${!m.active})">${m.active?'Stop':'Start'}</button></td></tr>`}).join('')
  :'<tr><td colspan="6" class="empty">No shops here</td></tr>'}
async function tog(id,a){if(!a&&!confirm('Stop this shop? Its phones are logged out and the voice stops.'))return;
 await api('/admin/merchants/'+id,{method:'PATCH',body:JSON.stringify({active:a})});toast(a?'Shop started':'Shop stopped');load()}

// ---------- shop detail ----------
async function openShop(id,quiet){S=await api('/admin/merchants/'+id);if(!quiet)edit=false;drawShop();$('drawer').classList.add('on');$('veil').classList.add('on')}
function closeShop(){$('drawer').classList.remove('on');$('veil').classList.remove('on')}
function drawShop(){const m=S.merchant,[c,t]=apText(m);
 const f=(l,v)=>`<div class="fact"><small>${l}</small><b>${v}</b></div>`;
 $('drawer').innerHTML=`<div class="dhead">${av(m)}<div style="min-width:0"><h2>${esc(m.name)||'No shop name'}</h2><span class="pill p-${m.status}">${LABEL[m.status]}</span></div>
  <button class="x" onclick="closeShop()" aria-label="Close">✕</button></div>
 <div class="facts">
  ${f('Plan until',m.plan_until?`${dd(m.plan_until)}<br><span class="${m.plan_active?'ok':'bad'}" style="font-size:12px">${left(m.plan_until)}</span>`:'<span class="dim">No plan</span>')}
  ${f('AutoPay',`<span class="ap"><span class="dot" style="background:${c}"></span>${t}</span><span class="dim" style="font-size:12px;font-weight:500">${m.autopay_checked_at?'checked '+ago(m.autopay_checked_at):'not checked yet'}</span>`)}
  ${f('Paid to you',m.paid_count?`${rs(m.paid_total)} <span class="dim" style="font-size:12px;font-weight:500">· ${m.paid_count}×</span>`:'<span class="dim">Nothing yet</span>')}
  ${f('Last seen',m.online?'<span class="ok">● Online</span>':ago(m.last_seen))}</div>
 <div class="row"><button class="pur grow" onclick="checkAp(this)">⟳ Check AutoPay</button>
  <button class="sec grow" onclick="edit=!edit;drawShop()">${edit?'Cancel edit':'✎ Edit details'}</button>
  <button class="${m.active?'danger':''} grow" onclick="tog(${m.id},${!m.active})">${m.active?'Stop shop':'Start shop'}</button></div>
 ${edit?`<div class="sec-t">Edit details</div><div class="grid" style="grid-template-columns:1fr 1fr;gap:10px">
  ${['name:Shop name','email:Google email','phone:Phone','upi_id:UPI ID','city:City'].map(x=>{const [k,l]=x.split(':');return `<input id="ed_${k}" value="${esc(m[k])}" placeholder="${l}" aria-label="${l}">`}).join('')}
  <button onclick="saveEdit(this)">Save</button></div>`:
 `<div class="sec-t">Details</div>
  <div class="li"><span class="dim" style="width:90px">Email</span><span class="grow">${esc(m.email)||'—'}</span></div>
  <div class="li"><span class="dim" style="width:90px">Phone</span><span class="grow">${esc(m.phone)||'—'}</span></div>
  <div class="li"><span class="dim" style="width:90px">UPI ID</span><span class="grow">${esc(m.upi_id)||'<span class="bad">not set</span>'}</span></div>
  <div class="li"><span class="dim" style="width:90px">City</span><span class="grow">${esc(m.city)||'—'}</span></div>
  <div class="li"><span class="dim" style="width:90px">Joined</span><span class="grow">${dd(m.created_at)} · ${m.devices} phone(s)</span></div>`}
 <div class="sec-t">Give free days</div>
 <div class="row"><input id="fdD" type="number" min="1" max="90" value="7" style="width:80px" aria-label="Days">
  <input id="fdR" class="grow" placeholder="Reason (needed)"><button onclick="freeDays(this)">Give</button></div>
 <div class="sec-t">Payments</div>
 ${S.charges.length?S.charges.map(x=>`<div class="li"><span class="dot" style="background:var(--green)"></span><span class="grow">${dt(x.paid_at)} <span class="dim">· ${esc(x.method)}</span></span><b>${rs(x.amount)}</b></div>`).join('')
  :'<div class="dim" style="font-size:13px">No payments yet</div>'}
 <div class="sec-t">History</div>
 ${S.log.length?S.log.slice(0,12).map(l=>`<div class="li"><span class="grow">${esc(l.detail||l.action)}</span><span class="dim" style="flex:none">${ago(l.created_at)}</span></div>`).join('')
  :'<div class="dim" style="font-size:13px">Nothing yet</div>'}`}
async function checkAp(b){busy(b,true);try{const r=await post(`/admin/merchants/${S.merchant.id}/autopay-check`);S=r;
 toast(r.report.checked?'AutoPay: '+apText(S.merchant)[1]:'Razorpay has no AutoPay for this shop yet');drawShop();load()}finally{busy(b,false)}}
async function saveEdit(b){const body={};['name','email','phone','upi_id','city'].forEach(k=>body[k]=$('ed_'+k).value.trim());
 busy(b,true);try{S=await api('/admin/merchants/'+S.merchant.id,{method:'PATCH',body:JSON.stringify(body)});edit=false;toast('Saved');drawShop();load()}finally{busy(b,false)}}
async function freeDays(b){const days=+$('fdD').value,reason=$('fdR').value.trim();if(reason.length<3){toast('Write a short reason');return}
 if(!confirm(`Give ${days} free day(s)?`))return;busy(b,true);try{S=await post(`/admin/merchants/${S.merchant.id}/free-days`,{days,reason});toast('+'+days+' days given');drawShop();load()}finally{busy(b,false)}}

// ---------- autopay ----------
function renderAutopay(){const s=D.autopay_sync||{},st=D.stats.setup;
 $('syncInfo').innerHTML=!st.razorpay_keys?'<div class="banner" style="margin:0">Set the Razorpay API keys on Vercel to turn on the automatic check.</div>'
  :`<div class="grid stats">${[['Last check',s.at?ago(s.at):'never',s.source==='daily'?'nightly':s.at?'manual':''],['Checked',s.checked||0,'AutoPays'],
   ['New matched',s.matched_new||0,'linked to a shop'],['Updated',s.updated||0,(s.charges_added||0)+' charge(s) added']]
   .map(x=>`<div class="stat" style="--glow:var(--purple);--tint:var(--purple-d);cursor:default"><small>${x[0]}</small><b style="font-size:24px">${x[1]}</b><em>${x[2]}</em></div>`).join('')}</div>
   ${s.partial?'<div class="banner" style="margin-top:12px">Not finished – press “Check with Razorpay” again.</div>':''}`;
 const opts=D.merchants.slice().sort((a,b)=>String(a.name||a.email).localeCompare(String(b.name||b.email))).map(m=>`<option value="${m.id}">${esc(m.name||'(no name)')} – ${esc(m.email)}</option>`).join('');
 $('unmatched').innerHTML=D.unmatched.length?D.unmatched.map(u=>`<div class="li" style="flex-wrap:wrap"><div class="grow"><b>${esc([u.email,u.phone,u.vpa].filter(Boolean).join(' · ')||u.rzp_sub_id)}</b>
  <div class="dim" style="font-size:12px">${esc(u.rzp_sub_id)} · ${esc(u.status)} · ${dd(u.created_at)}</div></div>
  <select id="lk_${esc(u.rzp_sub_id)}" style="max-width:240px"><option value="">Pick the shop…</option>${opts}</select>
  <button class="sm" onclick="linkAp('${esc(u.rzp_sub_id)}',this)">Link</button><button class="sm sec" onclick="ignoreAp('${esc(u.rzp_sub_id)}')">Ignore</button></div>`).join('')
  :'<div class="empty"><span class="ok">✓</span> Every AutoPay belongs to a shop</div>';
 $('pending').innerHTML=D.pending.length?D.pending.map(x=>`<div class="li"><div class="grow"><b>${esc(x.name)||esc(x.email)}</b><div class="dim" style="font-size:12px">${rs(x.amount)} · ${ago(x.created_at)}</div></div>
  <button class="sm" onclick="appr(${x.id})">Approve</button><button class="sm danger" onclick="rej(${x.id})">Reject</button></div>`).join('')
  :'<div class="empty">Nothing waiting</div>'}
async function syncAll(b){busy(b,true);try{const r=await post('/admin/autopay/sync');toast(`Checked ${r.checked}: ${r.matched_new} new, ${r.updated} updated`);await load()}finally{busy(b,false)}}
async function linkAp(id,b){const mid=+$('lk_'+id).value;if(!mid){toast('Pick the shop first');return}
 busy(b,true);try{await post('/admin/autopay/link',{rzp_sub_id:id,merchant_id:mid});toast('Linked');await load()}finally{busy(b,false)}}
async function ignoreAp(id){if(!confirm('Ignore this AutoPay? It is not for a Payvoro shop.'))return;await post('/admin/autopay/ignore',{rzp_sub_id:id});load()}
async function appr(id){if(!confirm('Did you receive this payment in Razorpay?'))return;await post('/admin/subscriptions/'+id+'/approve');toast('Approved: +30 days');load()}
async function rej(id){if(!confirm('Reject this payment?'))return;await post('/admin/subscriptions/'+id+'/reject');load()}

// ---------- setup ----------
function renderSetup(){const s=D.stats,st=s.setup,p=s.plans[0];
 const ck=(c,t,h)=>`<div class="ck"><span class="i ${c}">${c==='y'?'✓':c==='w'?'!':'✕'}</span><div style="min-width:0"><b>${t}</b><div class="dim" style="font-size:12.5px">${h}</div></div></div>`;
 $('setup').innerHTML=ck(st.database==='postgres'?'y':st.database_ok?'w':'n','Database',st.database==='postgres'?'Neon Postgres – data is safe':'SQLite file (fine on your PC only)')+
  ck(st.razorpay_keys?(st.razorpay_mode==='live'?'y':'w'):'n','Razorpay API keys'+(st.razorpay_mode?' ('+st.razorpay_mode+')':''),st.razorpay_keys?'AutoPay is checked automatically':'Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET')+
  ck(st.webhook_secret?'y':'w','Webhook (instant)',`Razorpay → Webhooks → <code>${esc(D.webhook_url)}</code> · secret = RAZORPAY_WEBHOOK_SECRET · events subscription.*`)+
  ck(st.cron_secret?'y':'w','Nightly AutoPay check',st.cron_secret?'Runs every night at 2 AM':'Set CRON_SECRET (any long random text), then redeploy')+
  ck(st.google_login?'y':'n','Google login',st.google_login?'GOOGLE_WEB_CLIENT_ID is set':'Set GOOGLE_WEB_CLIENT_ID')+
  ck(st.dev_mode?'n':'y','Test mode off',st.dev_mode?'Turn off PAYVORO_DEV':'Only real Google logins');
 $('plan').innerHTML=p?`<div class="big">${rs(p.price)}<small>/ month · ₹${esc(p.per_day)}/day in app</small></div>
  <div class="li" style="margin-top:10px"><span class="dim grow">Paying</span><b>${p.paying}</b></div><div class="li"><span class="dim grow">Free trial</span><b>${p.trial}</b></div>
  <div class="li"><span class="dim grow">AutoPay on</span><b>${p.autopay_on}</b></div>
  <div class="li"><span class="dim grow">Razorpay plan</span>${p.rzp_plan_id?`<code>${esc(p.rzp_plan_id)}</code>`:'<span class="warn">not set</span>'}</div>
  <div class="li"><span class="dim grow">AutoPay link</span>${p.link?`<a href="${esc(p.link)}" target="_blank" rel="noopener">open ↗</a>`:'<span class="warn">not set</span>'}</div>`:''}

$('addBtn').onclick=async()=>{await post('/admin/merchants',{name:$('n').value,email:$('e').value,phone:$('p').value||null,upi_id:$('u').value||null,plan:'none',months:1});
 ['n','e','p','u'].forEach(i=>$(i).value='');addDlg.close();toast('Shop added');load()};

$('key').value=K;load().catch(()=>{});
setInterval(()=>{if(K&&!document.hidden&&!$('drawer').classList.contains('on')&&!$('addDlg').open)load().catch(()=>{})},60000);
</script></body></html>"""
