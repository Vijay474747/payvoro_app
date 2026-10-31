package com.payvoro.app.data

import android.content.Context
import androidx.room.*
import kotlinx.coroutines.flow.Flow

const val SUCCESS = "SUCCESS"
const val FAILED = "FAILED"

@Entity(tableName = "payments", indices = [Index(value = ["dedupeKey"], unique = true)])
data class Payment(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val amount: Double,
    val payer: String?,
    val app: String,          // id from UpiApps (gpay, phonepe, ...)
    val status: String,       // SUCCESS or FAILED
    val rawText: String,      // kept only on the phone, never sent to the server
    val timestamp: Long,
    val dedupeKey: String,
    val synced: Boolean = false,
    // ---- verification (DB v2) ----
    val utr: String? = null,                                         // 12-digit UPI reference, if found
    @ColumnInfo(defaultValue = "app") val source: String = "app",    // "app" = UPI app alert, "bank" = bank SMS only
    @ColumnInfo(defaultValue = "0") val bankConfirmed: Boolean = false, // bank SMS also arrived for this payment
)

const val SOURCE_APP = "app"
const val SOURCE_BANK = "bank"

@Dao
interface PaymentDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(p: Payment): Long

    @Query("SELECT * FROM payments ORDER BY timestamp DESC")
    fun all(): Flow<List<Payment>>

    @Query("SELECT * FROM payments WHERE synced = 0 ORDER BY timestamp LIMIT 200")
    suspend fun unsynced(): List<Payment>

    @Query("UPDATE payments SET synced = 1 WHERE id IN (:ids)")
    suspend fun markSynced(ids: List<Long>)

    /** Oldest app-alert payment of this amount that has no bank SMS yet (so 2 × ₹10 match in order). */
    @Query("SELECT * FROM payments WHERE source = 'app' AND bankConfirmed = 0 AND status = 'SUCCESS' AND amount = :amount AND timestamp BETWEEN :from AND :to ORDER BY timestamp ASC LIMIT 1")
    suspend fun findAppPaymentToConfirm(amount: Double, from: Long, to: Long): Payment?

    /** A bank-SMS-only payment that came BEFORE the app alert. */
    @Query("SELECT * FROM payments WHERE source = 'bank' AND status = 'SUCCESS' AND amount = :amount AND timestamp >= :from ORDER BY timestamp ASC LIMIT 1")
    suspend fun findBankOnly(amount: Double, from: Long): Payment?

    @Query("UPDATE payments SET bankConfirmed = 1, utr = COALESCE(utr, :utr), synced = 0 WHERE id = :id")
    suspend fun confirmByBank(id: Long, utr: String?)

    @Query("UPDATE payments SET source = 'app', app = :app, payer = COALESCE(:payer, payer), utr = COALESCE(utr, :utr), synced = 0 WHERE id = :id")
    suspend fun upgradeToApp(id: Long, app: String, payer: String?, utr: String?)

    @Query("SELECT * FROM payments WHERE utr = :utr LIMIT 1")
    suspend fun findByUtr(utr: String): Payment?
}

val MIGRATION_1_2 = object : androidx.room.migration.Migration(1, 2) {
    override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE payments ADD COLUMN utr TEXT")
        db.execSQL("ALTER TABLE payments ADD COLUMN source TEXT NOT NULL DEFAULT 'app'")
        db.execSQL("ALTER TABLE payments ADD COLUMN bankConfirmed INTEGER NOT NULL DEFAULT 0")
    }
}

@Database(entities = [Payment::class], version = 2, exportSchema = false)
abstract class AppDatabase : RoomDatabase() {
    abstract fun payments(): PaymentDao

    companion object {
        @Volatile private var instance: AppDatabase? = null
        fun get(ctx: Context): AppDatabase = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(ctx.applicationContext, AppDatabase::class.java, "payvoro.db")
                .addMigrations(MIGRATION_1_2)
                .build().also { instance = it }
        }
    }
}

data class UpiApp(val id: String, val name: String, val packages: List<String>, val defaultOn: Boolean = true)

object UpiApps {
    // Built-in trusted apps. Only notifications from these exact package names count as payments.
    // Other payment apps (BharatPe, bank apps…) are detected and the merchant trusts them once.
    val all = listOf(
        UpiApp("gpay", "Google Pay", listOf("com.google.android.apps.nbu.paisa.user", "com.google.android.apps.nbu.paisa.merchant")),
        UpiApp("phonepe", "PhonePe", listOf("com.phonepe.app", "com.phonepe.app.business")),      // incl. PhonePe Business
        UpiApp("paytm", "Paytm", listOf("net.one97.paytm", "com.paytm.business")),                 // incl. Paytm for Business
        UpiApp("bhim", "BHIM", listOf("in.org.npci.upiapp")),
        UpiApp("amazon", "Amazon Pay", listOf("in.amazon.mShop.android.shopping"), defaultOn = false),
        UpiApp("bank", "Bank SMS", listOf(          // SMS apps: their messages go through the strict bank SMS check
            "com.google.android.apps.messaging", "com.samsung.android.messaging", "com.android.mms",
            "com.truecaller", "com.oneplus.mms", "com.motorola.messaging", "com.miui.smsextra")),
    )
    fun forPackage(pkg: String) = all.firstOrNull { pkg in it.packages }
    /** Trusted extra apps are stored with id "other:<App name>". */
    fun name(id: String) = all.firstOrNull { it.id == id }?.name ?: id.removePrefix("other:")
}

class Prefs(ctx: Context) {
    private val sp = ctx.applicationContext.getSharedPreferences("payvoro", Context.MODE_PRIVATE)
    private fun str(k: String, d: String) = sp.getString(k, d) ?: d
    private fun put(k: String, v: String) = sp.edit().putString(k, v).apply()
    private fun putB(k: String, v: Boolean) = sp.edit().putBoolean(k, v).apply()

    var merchantName: String get() = str("merchant_name", "My Shop"); set(v) = put("merchant_name", v)
    var upiId: String get() = str("upi_id", ""); set(v) = put("upi_id", v)
    var language: String get() = str("language", "ta"); set(v) = put("language", v)   // ta / en / hi (Tamil first)
    var soundOn: Boolean get() = sp.getBoolean("sound_on", true); set(v) = putB("sound_on", v)
    var soundBoxActive: Boolean get() = sp.getBoolean("active", true); set(v) = putB("active", v)
    var qrRaw: String get() = str("qr_raw", ""); set(v) = put("qr_raw", v)   // the shop's original QR text

    // ---- login (Google) ----
    var token: String get() = str("token", ""); set(v) = put("token", v)
    var email: String get() = str("email", ""); set(v) = put("email", v)
    var phone: String get() = str("phone", ""); set(v) = put("phone", v)
    val loggedIn: Boolean get() = token.isNotBlank()
    /** Shop name + UPI ID saved once (setup page). */
    val shopReady: Boolean get() = upiId.isNotBlank() && sp.contains("merchant_name")

    // ---- plan (refreshed from the server) ----
    var plan: String get() = str("plan", "none"); set(v) = put("plan", v)        // basic / plus (old: trial)
    var planUntil: Long get() = sp.getLong("plan_until", 0); set(v) = sp.edit().putLong("plan_until", v).apply()
    var onTrial: Boolean get() = sp.getBoolean("on_trial", false); set(v) = putB("on_trial", v)
    /** Razorpay UPI AutoPay: "" (never) / authenticated / active / pending / halted / cancelled */
    var autopayStatus: String get() = str("autopay_status", ""); set(v) = put("autopay_status", v)
    /** True until the merchant sets AutoPay the first time. The app shows Plans before Home. */
    var needsPlan: Boolean get() = sp.getBoolean("needs_plan", planUntil == 0L); set(v) = putB("needs_plan", v)

    fun planActive() = planUntil > System.currentTimeMillis()
    fun hasAutopay() = autopayStatus in setOf("authenticated", "active")
    /** Plus = says the customer's name + Hindi + analytics. Old "trial" accounts keep Plus features. */
    fun isPlus() = planActive() && plan in setOf("plus", "trial")
    /** Voice keeps working for 3 days after expiry, so the shop is not cut off suddenly. */
    fun canAnnounce() = planUntil + GRACE_MS > System.currentTimeMillis()
    fun daysLeft() = ((planUntil - System.currentTimeMillis()) / 86_400_000L).toInt()
    fun planLabel(): String {
        val name = when (plan) { "trial" -> "Free Trial"; "basic" -> "Basic"; "plus" -> "Plus"; else -> "No plan" }
        return if (onTrial && planActive() && plan != "trial") "$name · Free Trial" else name
    }

    // ---- verification settings ----
    /** Last 4 digits of the shop's bank account. Bank SMS must mention it. (Never the full number.) */
    var accountLast4: String get() = str("acct_last4", ""); set(v) = put("acct_last4", v.filter { it.isDigit() }.takeLast(4))
    /** Speak bank-SMS-only payments? Off by default because bank SMS can be late (e.g. Grama Bank). */
    var announceBankSms: Boolean get() = sp.getBoolean("announce_bank_sms", false); set(v) = putB("announce_bank_sms", v)

    private fun strSet(k: String): Set<String> = sp.getStringSet(k, emptySet())?.toSet() ?: emptySet()
    private fun putSet(k: String, v: Set<String>) = sp.edit().putStringSet(k, v).apply()

    /** Bank SMS senders the merchant trusted (e.g. their Grama Bank header). */
    fun trustedSenders(): Set<String> = strSet("trusted_senders")
    /** New bank-looking senders seen with a credit SMS: "BRAND|sample text". */
    fun candidateSenders(): List<Pair<String, String>> = strSet("cand_senders").map { it.substringBefore('|') to it.substringAfter('|') }
    fun addCandidateSender(brand: String, sample: String) {
        if (brand in trustedSenders() || brand in strSet("ignored_senders")) return
        val cur = strSet("cand_senders").filterNot { it.startsWith("$brand|") }.take(9)
        putSet("cand_senders", (cur + "$brand|${sample.take(140)}").toSet())
    }
    fun trustSender(brand: String) {
        putSet("trusted_senders", trustedSenders() + brand)
        putSet("cand_senders", strSet("cand_senders").filterNot { it.startsWith("$brand|") }.toSet())
    }
    fun ignoreSender(brand: String) {
        putSet("ignored_senders", strSet("ignored_senders") + brand)
        putSet("cand_senders", strSet("cand_senders").filterNot { it.startsWith("$brand|") }.toSet())
    }
    fun untrustSender(brand: String) = putSet("trusted_senders", trustedSenders() - brand)

    /** Extra payment apps the merchant trusted: "package|App name". */
    fun customApps(): List<Pair<String, String>> = strSet("custom_apps").map { it.substringBefore('|') to it.substringAfter('|') }
    fun customAppFor(pkg: String): UpiApp? = customApps().firstOrNull { it.first == pkg }
        ?.let { UpiApp("other:${it.second}", it.second, listOf(it.first)) }
    fun candidateApps(): List<Pair<String, String>> = strSet("cand_apps").map { it.substringBefore('|') to it.substringAfter('|') }
    fun addCandidateApp(pkg: String, label: String) {
        if (customAppFor(pkg) != null || pkg in strSet("ignored_apps")) return
        val cur = strSet("cand_apps").filterNot { it.startsWith("$pkg|") }.take(9)
        putSet("cand_apps", (cur + "$pkg|$label").toSet())
    }
    fun trustApp(pkg: String, label: String) {
        putSet("custom_apps", strSet("custom_apps") + "$pkg|$label")
        putSet("cand_apps", strSet("cand_apps").filterNot { it.startsWith("$pkg|") }.toSet())
    }
    fun ignoreApp(pkg: String) {
        putSet("ignored_apps", strSet("ignored_apps") + pkg)
        putSet("cand_apps", strSet("cand_apps").filterNot { it.startsWith("$pkg|") }.toSet())
    }
    fun untrustApp(pkg: String) = putSet("custom_apps", strSet("custom_apps").filterNot { it.startsWith("$pkg|") }.toSet())

    fun logout() = sp.edit().remove("token").apply().also {
        if (!com.payvoro.app.BuildConfig.DEMO_MODE) sp.edit()
            .remove("email").remove("phone").remove("plan").remove("plan_until").remove("on_trial")
            .remove("autopay_status").remove("needs_plan").remove("merchant_name").remove("upi_id").remove("qr_raw")
            .apply()
    }

    companion object { const val GRACE_MS = 3 * 86_400_000L }

    fun isAppEnabled(id: String): Boolean =
        sp.getBoolean("app_$id", UpiApps.all.firstOrNull { it.id == id }?.defaultOn ?: false)
    fun setAppEnabled(id: String, on: Boolean) = putB("app_$id", on)
}
