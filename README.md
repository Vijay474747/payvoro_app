# Payvoro – Payment Soundbox App

Turns any Android phone into a UPI sound box.
When a customer pays by GPay / PhonePe / Paytm / BHIM / bank UPI, the phone says
**"500 ரூபாய் பெறப்பட்டது"** (Tamil, English or Hindi) and shows a big green screen.
On the Plus plan it also says the customer's name.

## What is new in v2.0 (same design and colours)

| # | Change |
|---|---|
| 1 | **Google login.** Mobile number + OTP login is removed. |
| 2 | **Prices shown per day:** Basic **₹1.8/day**, Plus **₹3.5/day**. Collected **monthly** by UPI AutoPay (₹54 / ₹105). **Free trial: 3 days** (first plan only). |
| 3 | **Basic speaks Tamil** ("100 ரூபாய் பெறப்பட்டது"). **Plus also says the customer's name** ("ரமேஷ் அவர்களிடமிருந்து 100 ரூபாய் பெறப்பட்டது") when the UPI app shows a name. |
| 4 | **Profile:** shop name and UPI ID are saved and shown as a card, with an **Edit** button below. Changing the UPI ID asks "Are you sure?". |
| 5 | **Home:** "Test Sound Box" replaced by an **Upgrade Plan** button. Test Sound is in ⚙ Live Status and Profile → Sound Settings. |
| 6 | **Flow:** Google login → shop setup (scan QR) → choose plan + **UPI AutoPay** → Home. Home opens only after AutoPay is set. |
| 7 | **Razorpay UPI AutoPay** (subscriptions). Your links `rzp.io/rzp/yONA0V4T` (Basic) and `rzp.io/rzp/qTp7E5Ai` (Plus) are used. `razorpay.me/@payvoro_sound_box_app` stays as a backup "pay 1 month by link". |

No hardware. No new bank account. The merchant keeps their existing UPI QR.

## Folder layout

```
payvoro/
├── app/                      Android app (Kotlin + Jetpack Compose)
│   └── src/main/java/com/payvoro/app/
│       ├── PayvoroApp.kt              app start, shared state
│       ├── data/Data.kt               Room database, settings, plan, UPI app list
│       ├── service/
│       │   ├── PaymentListenerService.kt   reads payment notifications
│       │   ├── NotificationParser.kt       finds amount + payer, blocks duplicates
│       │   ├── SoundAnnouncer.kt           beep + voice (en / ta / hi)
│       │   ├── Api.kt                      server calls: Google login, plans, AutoPay
│       │   ├── GoogleAuth.kt               Google account picker
│       │   ├── UpiQrParser.kt              reads UPI ID from a scanned QR
│       │   └── Helpers.kt                  alerts, server sync, permission checks
│       └── ui/                        11 design screens + Login, QR Scan, Plans
└── backend/                  Server (Python FastAPI) – runs on Vercel
    ├── core.py               logic: Google login, plans, AutoPay, prices, payments (tested)
    ├── database.py           Neon Postgres on Vercel, SQLite file on your PC
    ├── main.py               web routes (Vercel finds the "app" here by itself)
    ├── admin_page.py         admin dashboard (/admin) + home page (/)
    ├── migrate_sqlite_to_postgres.py   copy an old payvoro.db into Neon (once)
    ├── vercel.json           region: Singapore (sin1), close to India
    ├── test_core.py
    └── test_main.py
```

## Deploy the backend on Vercel (step by step)

**1. Put the code on GitHub.** Make a new private repo and push the whole `payvoro` folder.

**2. Make the Vercel project.**
vercel.com → **Add New → Project** → import the repo →
**Root Directory: `backend`** → Framework Preset: **FastAPI** (Vercel finds it by itself) → **Deploy**.

**3. Add the database (Neon Postgres, free).**
Project → **Storage → Create Database → Neon** → region **Singapore** → **Connect** to the project.
This adds `DATABASE_URL` for you. The tables are made by themselves on the first request.

**4. Add environment variables.** Project → **Settings → Environment Variables**:

| Variable | Value |
|---|---|
| `PAYVORO_ADMIN_KEY` | a long password for the admin page (required) |
| `GOOGLE_WEB_CLIENT_ID` | Google Web client ID (same as in the app) |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | Razorpay → Account & Settings → API Keys (start with `rzp_test_…`) |
| `RAZORPAY_WEBHOOK_SECRET` | any secret word – type the same in Razorpay webhooks |
| `RAZORPAY_PLAN_BASIC` / `RAZORPAY_PLAN_PLUS` | optional – leave empty, the admin page can make the plans |

Do **not** set `PAYVORO_DEV` on Vercel. Then **Deployments → ⋯ → Redeploy** so the new values are used.

**5. Open the admin dashboard:** `https://YOUR-PROJECT.vercel.app/admin` → log in with `PAYVORO_ADMIN_KEY`.

**6. Set the AutoPay amount.** In **Plans & AutoPay amount**, type the monthly price for Basic and Plus and press
**Save amount**. With API keys, the server makes a Razorpay plan (`plan_…`) for that amount.
Do this once for each plan even if you keep ₹54 / ₹105, so both plans get a Razorpay plan ID.

**7. Add the Razorpay webhook.** Razorpay Dashboard → **Webhooks → Add New Webhook**:
URL = the one shown on the admin page (`https://YOUR-PROJECT.vercel.app/api/razorpay/webhook`, has a Copy button),
Secret = `RAZORPAY_WEBHOOK_SECRET`, events = all `subscription.*` events listed below.

**8. Point the app at Vercel.** `app/build.gradle.kts` → release `SERVER_URL` = your Vercel URL,
`DEMO_MODE` = `"false"` → build the release APK.

**9. Test with Razorpay test keys first**, then switch to `rzp_live_…` keys, press **Save amount** again
(live mode needs its own plans), and update the webhook in live mode.

**Already have a `payvoro.db` from an old server?** Copy it into Neon once:
`DATABASE_URL="<Neon URL>" python migrate_sqlite_to_postgres.py payvoro.db`

### Admin dashboard (`/admin`)

- **Top numbers:** total users, paying, free trial, AutoPay on (and failed), monthly income, all shops' sales today.
- **Users by plan:** Basic / Plus / Free trial / Expired / No plan / Stopped – tap one to filter the list.
- **Plans & AutoPay amount:** change the monthly price. The app shows the new per-day price at once.
  New merchants pay the new amount. Merchants already on AutoPay keep their old amount
  (Razorpay can't change a running AutoPay). Their webhooks are still recognised.
- **Razorpay & server setup:** green/red checklist (database, API keys, webhook, Google login, test mode).
- **Users list:** search, plan, AutoPay status and amount, plan end date, sales, last seen,
  History (AutoPay + customer payments), +1 month, change plan, Stop/Start.
- Pay-by-link approvals, latest AutoPay activity, Add merchant.

## Build the app

1. Install **Android Studio**. Open the `payvoro` folder. Gradle JDK = **Embedded JDK**.
2. Plug in a phone (USB debugging on) → press **Run** to test.

## Make an APK that installs on every phone (Android 7.0+)

**One time – create your signing key:**
```bash
cd payvoro
bash make-keystore.sh
```
This makes `payvoro-release.jks` + `keystore.properties`.
⚠️ Back up both and the password forever. Every update must use the same key.
(No key yet? The release APK is signed with the debug key so it still installs – fine for testing only.)

**Every time you want an APK for merchants:**
1. **Build → Select Build Variant → app: release**
2. **Build → Build App Bundle(s) / APK(s) → Build APK(s)**
3. File: `app/build/outputs/apk/release/app-release.apk` → share by WhatsApp / Drive / USB
4. For an update, raise `versionCode` (1 → 2 → 3…) in `app/build.gradle.kts` first.

Also done in the project: `android.injected.testOnly=false` (APKs from the Run button install on other
phones too), and v1 + v2 signing for old and new phones.

**Still "App not installed"?** Uninstall any old Payvoro first (different key) · phone must be Android 7.0+ ·
allow "Install unknown apps" · Play Protect → "Install anyway" · keep 200 MB free.

## Set up a merchant phone (5 minutes)

1. Install the APK.
2. **Android 13+ only:** App info → ⋮ (top right) → **Allow restricted settings**.
   Without this, Notification Access stays greyed out for apps not from Play Store.
3. Open Payvoro → **Enable** Notification Access → turn on Payvoro.
4. Allow notifications. Set battery to **Unrestricted**.
5. Xiaomi / Vivo / Oppo / Realme: also turn on **Autostart** and lock the app in recent apps.
6. **Continue with Google** (the phone needs a Google account).
7. **Setup:** tap **Scan my shop QR** → point the camera at the existing QR sticker (or pick a photo) → Save → Continue.
8. **Choose plan** → **Start 3 days free** → approve **UPI AutoPay** on the Razorpay page → come back. Home opens.
9. Profile → Sound Settings → **Test Sound**. Then do a real ₹1 payment to test.

## Demo mode (on now)

`app/build.gradle.kts` → `buildConfigField("Boolean", "DEMO_MODE", "true")`

- No server and no Google setup needed. **Continue with Google** logs in at once (fake account).
- The first plan starts a 3-day free trial at once. No Razorpay page, no money is taken.
- Payment detection, voice, QR scan and bank SMS checks all work normally on the phone.
- When your server is live, change it to `"false"` and set the release `SERVER_URL`.

## App flow

```
Splash → Google login → Setup (shop name + scan QR) → Plans (UPI AutoPay) → Permissions → Home
```

- **My QR:** scan the shop's existing sticker (camera or gallery). Works with `upi://` QRs,
  Bharat QR and plain UPI IDs. The app shows the shop's **own original QR**, so bank merchant
  details are kept. Amount QR is built on top of it.
- **Plans** (Profile → My Plan, or the Home banner):

| | Basic ₹1.8/day (₹54/month) | Plus ₹3.5/day (₹105/month) |
|---|---|---|
| Voice alerts | தமிழ் or English | தமிழ், English, हिंदी |
| Says the customer's name | – | ✓ |
| UPI apps + bank SMS | ✓ | ✓ |
| Scan / show / share QR | ✓ | ✓ |
| History | Last 30 days | Unlimited + cloud backup |
| Analytics | – | ✓ |

- Paid **monthly by Razorpay UPI AutoPay**. The app shows the per-day price big and the monthly amount small
  (the UPI AutoPay screen always shows the monthly amount, so merchants are not surprised).
- **3-day free trial** for the first plan: it starts when the merchant approves AutoPay. First charge after 3 days.
- Switching plan (Basic → Plus) makes a new AutoPay and stops the old one.
- "Can't use AutoPay? Pay 1 month by link" opens razorpay.me. You approve it on the admin page (+30 days).
- After expiry, voice keeps working **3 more days** (grace). Then payments are still saved,
  but there is no voice until renewal.
- Change prices and features in `backend/core.py` (`PLANS`) and `Api.defaultPlans` in the app.
  If you change a price, make a new Razorpay plan too (Razorpay plans can't change their amount).

## How Payvoro verifies a payment

No bank login, no account number, no PAN. Everything is read from notifications on the merchant's own phone.

| Step | Source | Rule | Result |
|---|---|---|---|
| 1 | **UPI app alert** – Google Pay, PhonePe (+ Business), Paytm (+ for Business), BHIM, Amazon Pay | Only these exact apps (Android gives the real package name – no other app can post as GPay). Must say "paid you / received / credited". Ignores sent, requests, refunds, cashback, "will be credited", alerts older than 10 min. | **✓ Verified** + instant voice |
| 2 | **Bank SMS** (Google Messages, Samsung, Truecaller…) | Sender must be a bank ID like `JD-HDFCBK-T` – phone numbers and contacts ignored. `-P` promotional SMS ignored. Must be a known bank or one the merchant trusted. No links / loan / offer / KYC / OTP. Must say credited and mention the account – and match the **last 4 digits** if saved. | Matches an app alert (same UTR, or same amount within 6 h) → **✓✓ Bank confirmed**, silent. No app alert → saved as "Bank SMS" (speaks only if turned on). |
| 3 | **Unknown app / new bank sender** | Never announced. Listed in *UPI App Selection* → merchant taps **Trust** once (e.g. BharatPe, the Grama Bank header). Chat/SMS-style apps can never be trusted as payment apps. | Merchant decides |

Late SMS (common with Grama Banks) never speaks a second time – it only adds the ✓✓ tick.
The same UTR is never counted twice. Two ₹10 payments are matched oldest-first.

Merchant setup for verification: *UPI App Selection* → enter account **last 4 digits** → trust the bank sender when it appears.
Tests: `BankSmsFilterTest.kt` (bank SMS rules), `NotificationParserTest.kt`, `UpiQrParserTest.kt`.

## Server address in the app

Edit `app/build.gradle.kts`:
- `debug` → `http://10.0.2.2:8000` (emulator). On a real phone use your PC's Wi-Fi IP, e.g. `http://192.168.1.5:8000`.
- `release` → your real `https://` server.

## Run the server

**Test mode** (no Google, no Razorpay):

```bash
cd backend
pip install -r requirements.txt
PAYVORO_DEV=1 PAYVORO_ADMIN_KEY=secret uvicorn main:app --host 0.0.0.0 --port 8000
```
In test mode the login token `dev:someone@gmail.com` works without Google (for testing only).

**Live mode** – set these environment variables:

| Variable | What |
|---|---|
| `PAYVORO_ADMIN_KEY` | Password for the admin page |
| `GOOGLE_WEB_CLIENT_ID` | Google login (same value as in the app – see below) |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | Razorpay API keys (best: AutoPay made for each merchant, no email typing) |
| `RAZORPAY_PLAN_BASIC`, `RAZORPAY_PLAN_PLUS` | Razorpay plan IDs (`plan_...`) for ₹54 and ₹105 monthly |
| `RAZORPAY_WEBHOOK_SECRET` | Webhook secret (see below) |
| `RAZORPAY_LINK_BASIC`, `RAZORPAY_LINK_PLUS` | Your AutoPay links. Default: `rzp.io/rzp/yONA0V4T` and `rzp.io/rzp/qTp7E5Ai` |
| `RAZORPAY_ME_LINK` | Backup pay-by-link page. Default: `razorpay.me/@payvoro_sound_box_app` |
| `ALLOW_SIGNUP=0` | Only Google emails you added in admin can log in |
| `TRIAL_DAYS` | Free trial length (default 3) |

Never use `PAYVORO_DEV=1` on the live server.

Your existing server database is upgraded by itself on the first start (old merchants, payments and
plans are kept; phone number becomes optional).

### Set up Google login (once)

1. **console.cloud.google.com** → new project "Payvoro" → **OAuth consent screen** → External → fill name and email.
2. **Credentials → Create OAuth client ID → Web application.** Copy the Client ID.
   Put it in `app/build.gradle.kts` (`GOOGLE_WEB_CLIENT_ID`) **and** on the server (`GOOGLE_WEB_CLIENT_ID`).
3. **Create OAuth client ID → Android.** Package `com.payvoro.app`. SHA-1 of your key:
   `keytool -list -v -keystore payvoro-release.jks -alias payvoro` (also add the debug key's SHA-1 for testing:
   `keytool -list -v -keystore ~/.android/debug.keystore -storepass android`).

### Set up UPI AutoPay (Razorpay, once)

1. Razorpay Dashboard → **Subscriptions → Plans**: make **Basic ₹54 monthly** and **Plus ₹105 monthly**.
   Your AutoPay links should use these same plans. Put the plan IDs in `RAZORPAY_PLAN_BASIC/PLUS`.
2. **Webhooks → Add** `https://YOUR_SERVER/api/razorpay/webhook` with a secret (= `RAZORPAY_WEBHOOK_SECRET`).
   Tick: `subscription.authenticated`, `subscription.activated`, `subscription.charged`,
   `subscription.pending`, `subscription.halted`, `subscription.cancelled`, `subscription.completed`.
3. Test with test keys first (`rzp_test_...`).

How the server picks the payment page, best first:

| Mode | When | How the merchant is found |
|---|---|---|
| **AutoPay made by the server** | API keys + plan IDs are set | Its own subscription per merchant. 3-day trial = first charge 3 days later. Fully automatic. |
| **Your AutoPay link** (rzp.io) | No API keys | The app asks the merchant to type the **same email as their Google login**. The webhook matches the email. |
| **Pay 1 month by link** (razorpay.me) | Merchant can't use AutoPay | You check Razorpay and **Approve** on the admin page. |

If AutoPay fails (low balance), voice keeps working for 3 more days, then stops until it is paid.

### Admin page – `https://YOUR_SERVER/admin`

- "Pay by link" payments waiting → Approve (+30 days) / Reject
- Add merchant by **Google email** (they then just log in with that Google account)
- Each shop: plan, trial, AutoPay status, today/month totals, last seen, plan expiry, +1 month, change plan, stop
- Monthly income (active Basic × 54 + Plus × 105, trials not counted)

### Tests

```bash
python test_core.py                     # Google login, trial, AutoPay webhooks, links, approvals, DB upgrade
pip install pytest httpx && pytest      # also the web routes
./gradlew test                          # (app folder) notification, name, bank SMS and QR parsers
```

### Login security

- Google checks the account. The server checks Google's signature on every login (`GOOGLE_WEB_CLIENT_ID`).
- Login tokens are stored only as hashes. Stopping a merchant in admin logs out all their phones.

## Things to know (honest limits)

- **Detection comes from phone notifications.** If the payment app does not show a
  notification (muted, logged out, no internet), Payvoro cannot announce it.
  Turn on **Bank SMS** too as a backup – duplicates are filtered.
- **It is not bank-level verification.** It is very good against fake payment
  screenshots, because only a real notification on the merchant's own phone triggers the voice.
- **"Payment Failed"** alerts are rare. Most UPI apps don't notify the receiver about failures.
- **Notification texts change.** When GPay/PhonePe change wording, update the word lists in
  `NotificationParser.kt` and add the new text to `NotificationParserTest.kt`.
- **Package names** in `Data.kt` (UpiApps): verify on real merchant phones, especially business apps.
- **Bank sender list** in `BankSmsFilter.kt` (`KNOWN_BANKS`) is a starting list. A missing bank (like the
  merchant's Grama Bank) appears under "New bank senders found" – trust it once. Collect real SMS samples
  from merchant phones and add them to `BankSmsFilterTest.kt`.
- **Play Store:** Notification Listener apps need a declaration form, privacy policy and a demo
  video. Sharing the APK directly is fine to start.
- **Play Store billing:** Google may ask for Google Play Billing instead of Razorpay for in-app plans.
  Razorpay is fine for APKs you share directly.
- **Customer name** comes from the UPI app notification. If the app shows no name (or only a number),
  Payvoro says only the amount.
- **Tamil voice** needs Google Text-to-speech with Tamil installed. Otherwise English is used.
- **Razorpay API:** all calls are in one small function in `core.py` (`rzp_request`). Check it against
  Razorpay's current docs before going live.
- Not compiled in this workspace (no Android SDK here). Expect to fix small things on first build.
