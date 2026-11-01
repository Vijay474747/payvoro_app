package com.payvoro.app.service

import android.content.Context
import android.os.Build
import com.payvoro.app.BuildConfig
import com.payvoro.app.data.Prefs
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

class ApiException(message: String, val code: Int) : Exception(message)

/** price = charged every month by UPI AutoPay. perDay = what the app shows big. */
data class Plan(val id: String, val name: String, val price: Int, val perDay: String, val features: List<String>)

/** method: autopay (Razorpay page made for this merchant) / link (your rzp.io AutoPay link) / manual (razorpay.me) / demo */
data class PayRequest(
    val method: String, val url: String, val amount: Int, val requestId: Long,
    val trial: Boolean = false, val email: String = "",
)

/** Talks to the Payvoro server. All calls are blocking – call them from Dispatchers.IO. */
object Api {
    private val base get() = BuildConfig.SERVER_URL.trimEnd('/')

    const val TRIAL_DAYS = 3
    const val RAZORPAY_ME_LINK = "https://razorpay.me/@payvoro_sound_box_app"

    val defaultPlans = listOf(
        Plan("basic", "Basic", 30, "1", listOf("Voice alert in Tamil (தமிழ்) or English", "All UPI apps + bank SMS", "Scan & show your shop QR", "30 days payment history (saved only on your phone)")),
    )

    private fun call(method: String, path: String, body: JSONObject? = null, token: String? = null): JSONObject {
        try {
            val conn = URL(base + path).openConnection() as HttpURLConnection
            conn.requestMethod = method
            conn.connectTimeout = 10_000
            conn.readTimeout = 15_000
            conn.setRequestProperty("Accept", "application/json")
            if (!token.isNullOrBlank()) conn.setRequestProperty("Authorization", "Bearer $token")
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json")
                conn.outputStream.use { it.write(body.toString().toByteArray()) }
            }
            val code = conn.responseCode
            val text = (if (code in 200..299) conn.inputStream else conn.errorStream)
                ?.bufferedReader()?.use { it.readText() }.orEmpty()
            conn.disconnect()
            val json = runCatching { JSONObject(text) }.getOrDefault(JSONObject())
            if (code !in 200..299) {
                val detail = json.opt("detail")
                throw ApiException(if (detail is String && detail.isNotBlank()) detail else "Server error ($code)", code)
            }
            return json
        } catch (e: IOException) {
            throw ApiException("No internet, or the server is not reachable. Please try again.", 0)
        }
    }

    private fun auth(ctx: Context): String = Prefs(ctx).token

    /** Saves name, UPI ID and plan from the server into the phone. */
    fun applyMerchant(ctx: Context, m: JSONObject) {
        val p = Prefs(ctx)
        m.optString("name").takeIf { it.isNotBlank() }?.let { p.merchantName = it }
        if (m.has("upi_id") && !m.isNull("upi_id")) p.upiId = m.getString("upi_id")
        m.optString("phone").takeIf { it.isNotBlank() && it != "null" }?.let { p.phone = it }
        m.optString("email").takeIf { it.isNotBlank() }?.let { p.email = it }
        m.optString("plan").takeIf { it.isNotBlank() }?.let { p.plan = it }
        if (m.has("plan_until")) p.planUntil = m.getLong("plan_until")
        if (m.has("on_trial")) p.onTrial = m.optBoolean("on_trial")
        if (m.has("autopay_status")) p.autopayStatus = m.optString("autopay_status")
        if (m.has("needs_plan")) p.needsPlan = m.optBoolean("needs_plan")
        // Only Tamil and English now (Hindi was in the removed Plus plan).
        if (p.language == "hi") p.language = "ta"
    }

    // ---------------- DEMO MODE ----------------
    /** true = everything works on the phone only (no server). Set in app/build.gradle.kts. */
    val demo: Boolean get() = BuildConfig.DEMO_MODE
    private const val DAY = 86_400_000L

    /** Google login. Returns true for a new merchant (needs shop setup). */
    fun loginWithGoogle(ctx: Context, idToken: String): Result<Boolean> = runCatching {
        val p = Prefs(ctx)
        if (demo) {
            Thread.sleep(500)
            p.token = "demo-google"
            if (p.email.isBlank()) p.email = "demo@payvoro.in"
            return@runCatching !p.shopReady
        }
        val body = JSONObject().put("id_token", idToken).put("device", "${Build.MANUFACTURER} ${Build.MODEL}")
        val res = call("POST", "/api/auth/google", body)
        p.token = res.getString("token")
        applyMerchant(ctx, res.getJSONObject("merchant"))
        res.optBoolean("is_new")
    }

    fun refreshMe(ctx: Context): Result<Unit> = runCatching {
        if (demo) return@runCatching
        try {
            applyMerchant(ctx, call("GET", "/api/me", token = auth(ctx)))
        } catch (e: ApiException) {
            if (e.code == 401 || e.code == 403) Prefs(ctx).logout()
            throw e
        }
    }

    fun updateMe(ctx: Context, name: String? = null, upiId: String? = null): Result<Unit> = runCatching {
        if (demo) {
            val p = Prefs(ctx)
            name?.let { p.merchantName = it }
            upiId?.let { p.upiId = it }
            return@runCatching
        }
        val body = JSONObject()
        name?.let { body.put("name", it) }
        upiId?.let { body.put("upi_id", it) }
        applyMerchant(ctx, call("PATCH", "/api/me", body, auth(ctx)))
    }

    fun plans(): Result<List<Plan>> = runCatching {
        if (demo) return@runCatching defaultPlans
        val arr = call("GET", "/api/plans").getJSONArray("plans")
        List(arr.length()) { i ->
            val o = arr.getJSONObject(i)
            val f = o.getJSONArray("features")
            Plan(o.getString("id"), o.getString("name"), o.getInt("price"), o.optString("per_day"),
                List(f.length()) { f.getString(it) })
        }
    }

    /** Starts UPI AutoPay for a plan. The app opens the returned Razorpay page. */
    fun subscribe(ctx: Context, planId: String): Result<PayRequest> = runCatching {
        if (demo) return@runCatching demoActivate(ctx, planId, autopay = true)
        val r = call("POST", "/api/subscribe", JSONObject().put("plan", planId), auth(ctx))
        PayRequest(r.getString("method"), r.getString("url"), r.getInt("amount"), r.getLong("request_id"),
            r.optBoolean("trial"), r.optString("email"))
    }

    /** Backup: pay one month on the razorpay.me page. Payvoro turns the plan on after checking. */
    fun payManually(ctx: Context, planId: String): Result<PayRequest> = runCatching {
        if (demo) return@runCatching demoActivate(ctx, planId, autopay = false)
        val r = call("POST", "/api/subscribe/manual", JSONObject().put("plan", planId), auth(ctx))
        PayRequest("manual", r.getString("url"), r.getInt("amount"), r.getLong("request_id"))
    }

    /** Demo only: no money. First plan gets the free trial, like the real server. */
    private fun demoActivate(ctx: Context, planId: String, autopay: Boolean): PayRequest {
        val plan = defaultPlans.first { it.id == planId }
        val p = Prefs(ctx)
        val now = System.currentTimeMillis()
        val trial = autopay && p.planUntil == 0L
        p.plan = planId
        p.planUntil = if (trial) now + TRIAL_DAYS * DAY else maxOf(now, p.planUntil) + 30 * DAY
        p.onTrial = trial
        if (autopay) p.autopayStatus = if (trial) "authenticated" else "active"
        p.needsPlan = false
        if (p.language == "hi") p.language = "ta"
        return PayRequest("demo", "", plan.price, 0, trial)
    }

    fun logout(ctx: Context) {
        if (!demo) runCatching { call("POST", "/api/auth/logout", JSONObject(), auth(ctx)) }
        Prefs(ctx).logout()
    }
    // Customer payments are never sent to the server (Razorpay review). They stay on the phone.
}
