"""HTML for the admin dashboard (/admin) and the home page (/). Plain HTML + JS, no build step."""

ADMIN_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Payvoro Admin</title>
<meta name="robots" content="noindex">
<style>
:root{--brand:#5b3fe8;--brand-d:#3a22b8;--brand-l:#ede9ff;--bg:#f6f5fb;--card:#fff;--ink:#16141f;--mute:#6b6880;
 --line:#ebe9f3;--ok:#15803d;--ok-l:#dcfce7;--bad:#dc2626;--bad-l:#fee2e2;--warn:#b45309;--warn-l:#fef3c7;
 --basic:#5b3fe8;--plus:#0e9f6e;--trial:#f59e0b;--expired:#ef4444;--none:#a8a5b8;--stopped:#44415a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{background:var(--brand-d);color:#fff;padding:14px 20px;display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:5}
header h1{font-size:18px;margin:0;flex:1;letter-spacing:.2px}header h1 span{opacity:.7;font-weight:500}
header button{background:#ffffff22;color:#fff}
main{max-width:1240px;margin:0 auto;padding:18px 16px 60px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:16px}
h2{font-size:15px;margin:0 0 4px}.sub{color:var(--mute);font-size:13px;margin:0 0 12px}
button{font:inherit;border:0;border-radius:9px;padding:8px 12px;background:var(--brand);color:#fff;cursor:pointer;font-weight:600}
button:hover{filter:brightness(1.07)}button.alt{background:var(--brand-l);color:var(--brand-d)}button.red{background:var(--bad)}
button.ghost{background:transparent;color:var(--brand-d);padding:6px 8px}button:disabled{opacity:.5;cursor:default}
input,select{font:inherit;padding:8px 10px;border:1px solid #d6d3e3;border-radius:9px;background:#fff;color:var(--ink);min-width:0}
input:focus,select:focus{outline:2px solid var(--brand);outline-offset:-1px}
.grid{display:grid;gap:12px}.tiles{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.tile{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
.tile small{color:var(--mute);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.4px}
.tile b{display:block;font-size:26px;margin-top:4px;font-variant-numeric:tabular-nums}.tile em{font-style:normal;color:var(--mute);font-size:12px}
.bar{display:flex;height:16px;border-radius:8px;overflow:hidden;background:var(--line);margin:10px 0 12px}
.bar i{display:block;height:100%}
.legend{display:flex;flex-wrap:wrap;gap:8px}
.chip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:#fff;border-radius:999px;padding:5px 11px;
 cursor:pointer;font-weight:600;color:var(--ink)}.chip.on{border-color:var(--brand);background:var(--brand-l)}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block}
.plans{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.plan{border:1px solid var(--line);border-radius:12px;padding:14px}.plan .price{font-size:28px;font-weight:800;color:var(--brand-d)}
.plan .price small{font-size:14px;color:var(--mute);font-weight:600}.kv{display:grid;grid-template-columns:110px 1fr;gap:4px 10px;font-size:13px;margin:10px 0}
.kv span{color:var(--mute)}.kv code{word-break:break-all}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.row input{flex:1;min-width:120px}
.wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;font-size:13px}th{color:var(--mute);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.3px}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:top;white-space:nowrap}
td.n{font-variant-numeric:tabular-nums}td small{color:var(--mute)}
.badge{display:inline-block;border-radius:6px;padding:2px 7px;font-size:12px;font-weight:700}
.b-basic{background:#ede9ff;color:var(--basic)}.b-plus{background:#d1fae5;color:#047857}.b-trial{background:var(--warn-l);color:var(--warn)}
.b-expired{background:var(--bad-l);color:var(--bad)}.b-no_plan{background:#f1f0f6;color:var(--mute)}.b-stopped{background:#e4e3ea;color:var(--stopped)}
.ok{color:var(--ok);font-weight:600}.bad{color:var(--bad);font-weight:600}.warn{color:var(--warn);font-weight:600}
.check{display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-bottom:1px solid var(--line)}.check:last-child{border:0}
.check .ic{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;font-size:13px;font-weight:800;flex:none}
.ic.y{background:var(--ok-l);color:var(--ok)}.ic.n{background:var(--bad-l);color:var(--bad)}.ic.w{background:var(--warn-l);color:var(--warn)}
.banner{border-radius:12px;padding:12px 14px;margin-bottom:12px;font-weight:600}.banner.bad{background:var(--bad-l);color:#991b1b}
.banner.warn{background:var(--warn-l);color:#92400e}
.two{display:grid;gap:16px;grid-template-columns:1fr}.two>*,.plans>*{min-width:0}.check code{word-break:break-all}
.check>div{min-width:0}@media(min-width:900px){.two{grid-template-columns:1.2fr 1fr}}
#login{max-width:380px;margin:12vh auto}#login input{width:100%;margin:10px 0}
#toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:#16141f;color:#fff;padding:10px 16px;border-radius:10px;
 display:none;z-index:20;max-width:90vw}
dialog{border:0;border-radius:14px;padding:0;width:min(760px,94vw);max-height:86vh}dialog::backdrop{background:#0006}
dialog .hd{display:flex;align-items:center;padding:14px 16px;border-bottom:1px solid var(--line)}dialog .hd h2{flex:1;margin:0}
dialog .bd{padding:14px 16px;overflow:auto;max-height:72vh}
details summary{cursor:pointer;font-weight:700;font-size:15px}details[open] summary{margin-bottom:10px}
.hidden{display:none!important}
</style></head><body>
<header><h1>Payvoro <span>Admin</span></h1><button id="refresh" class="hidden">Refresh</button><button id="logout" class="hidden">Log out</button></header>
<main>
 <div id="login" class="card"><h2>Admin login</h2><p class="sub">Enter your PAYVORO_ADMIN_KEY.</p>
  <input id="key" type="password" placeholder="Admin key" autocomplete="current-password"><button id="loginBtn" style="width:100%">Log in</button></div>

 <div id="app" class="hidden">
  <div id="banners"></div>
  <div class="grid tiles" id="tiles"></div>

  <div class="card" style="margin-top:16px"><h2>Users by plan</h2><p class="sub">Tap a plan to filter the user list.</p>
   <div class="bar" id="bar"></div><div class="legend" id="legend"></div></div>

  <div class="card"><h2>Plans &amp; AutoPay amount</h2>
   <p class="sub">Change the monthly amount charged by UPI AutoPay. With Razorpay API keys, a new Razorpay plan is made for you.
   New merchants pay the new amount. Merchants already on AutoPay keep their old amount.</p>
   <div class="grid plans" id="plans"></div></div>

  <div class="two">
   <div class="card wrap"><h2>Pay-by-link payments waiting</h2>
    <p class="sub">Merchants who paid one month on your razorpay.me page. Check your Razorpay dashboard, then approve (+30 days).</p>
    <table><thead><tr><th>#</th><th>Shop</th><th>Plan</th><th>Amount</th><th>Asked</th><th></th></tr></thead><tbody id="pending"></tbody></table></div>
   <div class="card"><h2>Razorpay &amp; server setup</h2><p class="sub">Everything should be green before you go live.</p><div id="setup"></div></div>
  </div>

  <div class="card"><div class="row" style="margin-bottom:10px"><h2 style="flex:1;margin:0">Users <span id="count" class="sub"></span></h2>
    <input id="q" placeholder="Search shop, email, UPI, city" style="max-width:300px"></div>
   <div class="legend" id="filters" style="margin-bottom:8px"></div>
   <div class="wrap"><table><thead><tr><th>#</th><th>Shop</th><th>Email</th><th>Plan</th><th>AutoPay</th><th>Plan until</th>
    <th>Today</th><th>Month</th><th>Last seen</th><th>Joined</th><th>Actions</th></tr></thead><tbody id="rows"></tbody></table></div></div>

  <div class="two">
   <div class="card wrap"><h2>Latest AutoPay &amp; payments</h2><p class="sub">Newest subscription requests from the app and Razorpay.</p>
    <table><thead><tr><th>#</th><th>Shop</th><th>Plan</th><th>₹</th><th>Way</th><th>Status</th><th>When</th></tr></thead><tbody id="recent"></tbody></table></div>
   <div class="card"><details><summary>Add merchant</summary>
    <p class="sub">The merchant then logs in to the app with this Google account.</p>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(160px,1fr))">
     <input id="n" placeholder="Shop name"><input id="e" placeholder="Google email"><input id="p" placeholder="Phone (optional)">
     <input id="u" placeholder="UPI ID (optional)"><input id="c" placeholder="City">
     <select id="pl"><option value="none">No plan (sets AutoPay in app)</option><option value="basic">Basic</option><option value="plus">Plus</option></select>
     <input id="mo" type="number" value="1" min="1" max="36" title="Months (paid plans)"></div>
    <button id="addBtn" style="margin-top:10px">Add merchant</button></details></div>
  </div>
 </div>
</main>
<dialog id="dlg"><div class="hd"><h2 id="dlgT">History</h2><button class="ghost" onclick="dlg.close()">Close ✕</button></div><div class="bd" id="dlgB"></div></dialog>
<div id="toast"></div>
<script>
const $=id=>document.getElementById(id);
const store={get(k){try{return localStorage.getItem(k)||''}catch(e){return ''}},set(k,v){try{v?localStorage.setItem(k,v):localStorage.removeItem(k)}catch(e){}}};
let K=store.get('pvk'), D=null, filter='all';
const COLORS={basic:'var(--basic)',plus:'var(--plus)',trial:'var(--trial)',expired:'var(--expired)',no_plan:'var(--none)',stopped:'var(--stopped)'};
const LABEL={basic:'Basic',plus:'Plus',trial:'Free trial',expired:'Expired',no_plan:'No plan',stopped:'Stopped'};
const rs=n=>'₹'+Number(n||0).toLocaleString('en-IN',{maximumFractionDigits:0});
const dt=t=>t?new Date(Number(t)).toLocaleString('en-IN',{dateStyle:'medium',timeStyle:'short'}):'—';
const dd=t=>t?new Date(Number(t)).toLocaleDateString('en-IN',{dateStyle:'medium'}):'—';
const ago=t=>{if(!t)return 'never';const s=(Date.now()-t)/1000;if(s<60)return 'just now';if(s<3600)return Math.floor(s/60)+' min ago';
 if(s<86400)return Math.floor(s/3600)+' h ago';return Math.floor(s/86400)+' d ago'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(m){const t=$('toast');t.textContent=m;t.style.display='block';clearTimeout(t._h);t._h=setTimeout(()=>t.style.display='none',3500)}
async function api(path,opt={}){opt.headers={'X-Admin-Key':K,'Content-Type':'application/json'};
 const r=await fetch(path,opt);const j=await r.json().catch(()=>({}));
 if(r.status===401){showLogin('Wrong admin key');throw new Error('401')}
 if(!r.ok){toast(typeof j.detail==='string'?j.detail:('Error '+r.status));throw new Error(r.status)}return j}
function showLogin(msg){$('login').classList.remove('hidden');$('app').classList.add('hidden');$('logout').classList.add('hidden');$('refresh').classList.add('hidden');if(msg)toast(msg)}
$('loginBtn').onclick=()=>{K=$('key').value.trim();store.set('pvk',K);load()};
$('key').onkeydown=e=>{if(e.key==='Enter')$('loginBtn').onclick()};
$('logout').onclick=()=>{K='';store.set('pvk','');$('key').value='';showLogin()};
$('refresh').onclick=()=>load();
$('q').oninput=()=>renderRows();

async function load(){ if(!K){showLogin();return}
 D=await api('/admin/dashboard');
 $('login').classList.add('hidden');$('app').classList.remove('hidden');$('logout').classList.remove('hidden');$('refresh').classList.remove('hidden');
 render()}

function render(){const s=D.stats, st=s.setup;
 let b='';
 if(!st.database_ok)b+='<div class="banner bad">⚠ No database connected on Vercel. Data will be lost. Add Neon Postgres in Vercel → Storage, then redeploy.</div>';
 if(st.dev_mode)b+='<div class="banner bad">⚠ PAYVORO_DEV=1 is on. Anyone can log in without Google. Turn it off on the live server.</div>';
 if(s.autopay_failed)b+=`<div class="banner warn">${s.autopay_failed} merchant(s) have a failed AutoPay charge (low balance or cancelled mandate).</div>`;
 $('banners').innerHTML=b;
 const T=[['Total users',s.total_users,`+${s.new_7_days} in 7 days`],['Paying',s.paying,'Basic + Plus'],['Free trial',s.by_status.trial,`${st.trial_days} days`],
  ['AutoPay on',s.autopay_on,s.autopay_failed?`${s.autopay_failed} failed`:'all fine'],['Monthly income',rs(s.monthly_income),'from paying AutoPay'],
  ['All shops today',rs(s.today_total),`${s.online} online now`]];
 $('tiles').innerHTML=T.map(t=>`<div class="tile"><small>${t[0]}</small><b>${t[1]}</b><em>${esc(t[2])}</em></div>`).join('');
 const total=s.total_users||1, keys=Object.keys(LABEL);
 $('bar').innerHTML=keys.map(k=>s.by_status[k]?`<i title="${LABEL[k]}: ${s.by_status[k]}" style="width:${s.by_status[k]/total*100}%;background:${COLORS[k]}"></i>`:'').join('');
 const chips=(withAll)=>(withAll?[`<span class="chip ${filter==='all'?'on':''}" data-f="all">All · ${s.total_users}</span>`]:[]).concat(keys.map(k=>
  `<span class="chip ${filter===k?'on':''}" data-f="${k}"><span class="dot" style="background:${COLORS[k]}"></span>${LABEL[k]} · ${s.by_status[k]||0}</span>`)).join('');
 $('legend').innerHTML=chips(false);$('filters').innerHTML=chips(true);
 document.querySelectorAll('.chip[data-f]').forEach(c=>c.onclick=()=>{filter=filter===c.dataset.f?'all':c.dataset.f;render();
  if(c.closest('#legend'))$('q').scrollIntoView({behavior:'smooth',block:'center'})});
 $('plans').innerHTML=s.plans.map(p=>`<div class="plan"><div class="row"><h2 style="flex:1;margin:0">${esc(p.name)}</h2>
  <span class="badge b-${p.id}">${p.paying} paying · ${p.trial} trial</span></div>
  <div class="price">${rs(p.price)} <small>/ month · ₹${esc(p.per_day)}/day shown in app</small></div>
  <div class="kv"><span>Razorpay plan</span>${p.rzp_plan_id?`<code>${esc(p.rzp_plan_id)}</code>`:'<span class="warn">not set</span>'}
  <span>AutoPay link</span>${p.link?`<code>${esc(p.link)}</code>`:'<span class="warn">not set</span>'}
  <span>AutoPay on</span><b>${p.autopay_on}</b></div>
  <div class="row"><input type="number" min="1" max="15000" id="price_${p.id}" value="${p.price}" style="max-width:110px" aria-label="Monthly amount">
   <span class="sub" style="margin:0" id="pd_${p.id}">= ₹${esc(p.per_day)}/day</span></div>
  <details style="margin-top:8px"><summary style="font-size:13px">Use my own Razorpay plan ID / AutoPay link</summary>
   <div class="grid" style="margin-top:6px"><input id="rid_${p.id}" placeholder="plan_... (leave empty = automatic)" value="">
   <input id="lnk_${p.id}" placeholder="https://rzp.io/... (only without API keys)" value="${esc(p.link)}"></div></details>
  <button style="margin-top:10px" onclick="savePlan('${p.id}')">Save amount</button></div>`).join('');
 s.plans.forEach(p=>{const i=$('price_'+p.id);i.oninput=()=>{const v=+i.value;$('pd_'+p.id).textContent=v>0?`= ₹${(Math.round(v/30*10)/10).toString()}/day`:''}});
 const ck=(state,title,hint)=>`<div class="check"><span class="ic ${state}">${state==='y'?'✓':state==='w'?'!':'✕'}</span><div><b>${title}</b><br><small class="sub">${hint}</small></div></div>`;
 $('setup').innerHTML=
  ck(st.database==='postgres'?'y':(st.database_ok?'w':'n'),'Database: '+(st.database==='postgres'?'Neon Postgres':'SQLite file'),st.database==='postgres'?'Data is saved safely.':'Fine on your PC. On Vercel connect Neon Postgres.')+
  ck(st.razorpay_keys?(st.razorpay_mode==='live'?'y':'w'):'n','Razorpay API keys'+(st.razorpay_mode?` (${st.razorpay_mode} mode)`:''),st.razorpay_keys?'Server makes each merchant\'s AutoPay and plans.':'Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in Vercel.')+
  ck(st.webhook_secret?'y':'n','Webhook secret',`Razorpay → Webhooks → add this URL with the same secret:<br><code>${esc(D.webhook_url)}</code> <button class="ghost" onclick="copyHook()">Copy</button>`)+
  ck(s.plans.every(p=>p.rzp_plan_id||p.link)?'y':'n','Plan for every price',s.plans.every(p=>p.rzp_plan_id)?'All plans have a Razorpay plan ID.':'Press "Save amount" on each plan after adding API keys to make the Razorpay plans.')+
  ck(st.google_login?'y':'n','Google login','GOOGLE_WEB_CLIENT_ID '+(st.google_login?'is set.':'is missing.'))+
  ck(st.dev_mode?'n':'y','Test mode off',st.dev_mode?'PAYVORO_DEV=1 – turn it off before going live.':'Only real Google logins work.');
 $('pending').innerHTML=D.pending.length?D.pending.map(x=>`<tr><td>#${x.id}</td><td>${esc(x.name)||'<i>not set</i>'}<br><small>${esc(x.email)}</small></td>
  <td><span class="badge b-${esc(x.plan)}">${esc(x.plan)}</span></td><td class="n">${rs(x.amount)}</td><td>${ago(x.created_at)}</td>
  <td><button onclick="appr(${x.id})">Approve</button> <button class="red" onclick="rej(${x.id})">Reject</button></td></tr>`).join('')
  :'<tr><td colspan="6" class="sub">Nothing waiting</td></tr>';
 $('recent').innerHTML=D.recent.length?D.recent.map(x=>`<tr><td>#${x.id}</td><td>${esc(x.name)||esc(x.email)}</td><td>${esc(x.plan)}${x.trial?' <small>trial</small>':''}</td>
  <td class="n">${rs(x.amount)}</td><td>${esc(x.method)}</td><td>${stBadge(x.status)}</td><td>${ago(x.created_at)}</td></tr>`).join('')
  :'<tr><td colspan="7" class="sub">No AutoPay yet</td></tr>';
 renderRows()}

const stBadge=s=>{const c={paid:'ok',authorised:'ok',pending:'warn',rejected:'bad'}[s]||'';return `<span class="${c}">${esc(s)}</span>`};
const apText=m=>{const s=m.autopay_status;if(!s)return '<small>—</small>';
 const c=(s==='active'||s==='authenticated')?'ok':(s==='cancelled'?'sub':'bad');return `<span class="${c}">${esc(s)}</span><br><small>${m.autopay_on?rs(m.autopay_amount)+'/month':''}</small>`};

function renderRows(){const q=$('q').value.trim().toLowerCase();
 const list=D.merchants.filter(m=>(filter==='all'||m.status===filter)&&(!q||[m.name,m.email,m.upi_id,m.city,m.phone].some(v=>String(v||'').toLowerCase().includes(q))));
 $('count').textContent=`· ${list.length} shown`;
 $('rows').innerHTML=list.length?list.map(m=>`<tr><td>${m.id}</td><td><b>${esc(m.name)||'<i>not set</i>'}</b><br><small>${esc(m.upi_id)} ${esc(m.city)}</small></td>
  <td>${esc(m.email)}<br><small>${esc(m.phone)}</small></td>
  <td><span class="badge b-${m.status}">${LABEL[m.status]}</span>${m.status==='trial'||m.status==='expired'?`<br><small>${esc(m.plan)}</small>`:''}</td>
  <td>${apText(m)}</td><td class="${m.plan_active?'ok':'bad'}">${m.plan_until?dd(m.plan_until):'—'}</td>
  <td class="n">${rs(m.today_total)} <small>(${m.today_count})</small></td><td class="n">${rs(m.month_total)}</td>
  <td class="${m.online?'ok':''}">${ago(m.last_seen)}</td><td>${dd(m.created_at)}</td>
  <td><button class="alt" onclick="hist(${m.id})">History</button> <button class="alt" onclick="ext(${m.id})">+1 month</button>
  <select onchange="setPlan(${m.id},this.value)" aria-label="Change plan"><option value="">plan…</option><option value="basic">Basic</option><option value="plus">Plus</option></select>
  <button class="${m.active?'red':''}" onclick="tog(${m.id},${!m.active})">${m.active?'Stop':'Start'}</button></td></tr>`).join('')
  :'<tr><td colspan="11" class="sub">No users here</td></tr>'}

async function savePlan(id){const price=+$('price_'+id).value, rid=$('rid_'+id).value.trim(), lnk=$('lnk_'+id).value.trim();
 const p=D.stats.plans.find(x=>x.id===id);
 if(price!==p.price&&!confirm(`Change ${p.name} AutoPay from ${rs(p.price)} to ${rs(price)} per month?\nNew merchants pay the new amount.`))return;
 const r=await api('/admin/plans/'+id,{method:'PUT',body:JSON.stringify({price,rzp_plan_id:rid||null,link:lnk})});
 toast(r.warning||(r.created_rzp_plan?`Saved. New Razorpay plan ${r.created_rzp_plan}`:'Saved'));load()}
function copyHook(){navigator.clipboard?.writeText(D.webhook_url).then(()=>toast('Webhook URL copied'),()=>toast(D.webhook_url))}
async function ext(id){await api('/admin/merchants/'+id,{method:'PATCH',body:JSON.stringify({extend_months:1})});toast('Added 1 month');load()}
async function setPlan(id,p){if(p){await api('/admin/merchants/'+id,{method:'PATCH',body:JSON.stringify({plan:p})});toast('Plan changed');load()}}
async function tog(id,a){if(!a&&!confirm('Stop this merchant? Their phones are logged out.'))return;
 await api('/admin/merchants/'+id,{method:'PATCH',body:JSON.stringify({active:a})});load()}
async function appr(id){if(confirm('Did you receive this payment in your Razorpay account?')){await api('/admin/subscriptions/'+id+'/approve',{method:'POST'});toast('Approved: +30 days');load()}}
async function rej(id){await api('/admin/subscriptions/'+id+'/reject',{method:'POST'});load()}
async function hist(id){const m=D.merchants.find(x=>x.id===id);
 const [subs,pays]=await Promise.all([api(`/admin/merchants/${id}/subscriptions`),api(`/admin/merchants/${id}/payments?limit=30`)]);
 $('dlgT').textContent=(m.name||m.email)+' – history';
 $('dlgB').innerHTML=`<h2>AutoPay &amp; plan payments</h2><div class="wrap"><table><thead><tr><th>#</th><th>Plan</th><th>₹</th><th>Way</th><th>Status</th><th>Razorpay</th><th>Asked</th><th>Paid</th></tr></thead><tbody>
 ${subs.length?subs.map(s=>`<tr><td>${s.id}</td><td>${esc(s.plan)}${s.trial?' <small>trial</small>':''}</td><td>${rs(s.amount)}</td><td>${esc(s.method)}</td><td>${stBadge(s.status)}</td>
 <td><small>${esc(s.provider_ref||s.payment_ref||'')}</small></td><td>${dt(s.created_at)}</td><td>${dt(s.paid_at)}</td></tr>`).join(''):'<tr><td colspan="8" class="sub">None</td></tr>'}
 </tbody></table></div><h2 style="margin-top:16px">Last customer payments</h2><div class="wrap"><table><thead><tr><th>When</th><th>₹</th><th>From</th><th>App</th><th>Check</th></tr></thead><tbody>
 ${pays.length?pays.map(p=>`<tr><td>${dt(p.ts)}</td><td class="n">${rs(p.amount)}</td><td>${esc(p.payer)}</td><td>${esc(p.app)}</td><td>${p.bank_confirmed?'✓✓ bank':'✓'}</td></tr>`).join(''):'<tr><td colspan="5" class="sub">None</td></tr>'}
 </tbody></table></div>`;$('dlg').showModal()}
$('addBtn').onclick=async()=>{await api('/admin/merchants',{method:'POST',body:JSON.stringify({name:$('n').value,email:$('e').value,
 phone:$('p').value||null,upi_id:$('u').value||null,city:$('c').value,plan:$('pl').value,months:+$('mo').value||1})});
 ['n','e','p','u','c'].forEach(i=>$(i).value='');toast('Merchant added');load()};
$('key').value=K; load().catch(()=>{}); setInterval(()=>{if(K&&!document.hidden&&!$('dlg').open)load().catch(()=>{})},60000);
</script></body></html>"""


HOME_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Payvoro Sound Box</title>
<meta name="description" content="Turn any Android phone into a UPI sound box. Voice alerts in Tamil, English and Hindi.">
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
<footer>Payvoro · <a href="/admin">Admin</a></footer>
<script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
fetch('/api/plans').then(r=>r.json()).then(d=>{document.getElementById('plans').innerHTML=d.plans.map(p=>`<div class="plan"><h2>${esc(p.name)}</h2>
<div class="price">₹${esc(p.per_day)}<small>/day</small></div><div class="month">₹${esc(p.price)} per month by UPI AutoPay · ${d.trial_days} days free</div>
<ul>${p.features.map(f=>`<li>${esc(f)}</li>`).join('')}</ul></div>`).join('')}).catch(()=>{});
</script></body></html>"""
