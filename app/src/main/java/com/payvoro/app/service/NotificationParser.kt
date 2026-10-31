package com.payvoro.app.service

import com.payvoro.app.data.FAILED
import com.payvoro.app.data.SUCCESS
import kotlin.math.abs

/**
 * Turns a notification's text into a payment, or null if it is not an incoming payment.
 * Pure Kotlin – easy to unit test. Tune the word lists with real notifications.
 */
object NotificationParser {
    data class Parsed(val amount: Double, val payer: String?, val status: String)

    private val amountRx = Regex("""(?:₹|\brs\.?|\binr)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)""", RegexOption.IGNORE_CASE)

    private val creditWords = listOf("paid you", "received", "credited", "sent you", "added to your")
    // Outgoing money, ads and reminders – never announce these
    private val outgoingWords = listOf("debited", "you paid", "paid to", "sent to", "you sent", "spent", "withdrawn")
    private val ignoreWords = listOf("request", "reminder", "cashback", "offer", "reward", "otp", "bill due", "emi", "win ", "loan",
        "will be credited", "to be credited", "refund", "scratch card", "http")
    private val failWords = listOf("failed", "declined", "unsuccessful")

    private val payerRx = listOf(
        Regex("""^(.+?)\s+(?:has\s+)?(?:paid|sent)\s+you""", RegexOption.IGNORE_CASE),
        Regex("""from\s+([A-Za-z][A-Za-z .]{1,40}?)(?:\s+(?:on|via|to|ref|upi)\b|[.,]|$)""", RegexOption.IGNORE_CASE),
    )

    fun parse(title: String, text: String): Parsed? {
        val full = "$title $text".replace('\n', ' ').trim()
        val lower = full.lowercase()
        val amount = amountRx.find(full)?.groupValues?.get(1)?.replace(",", "")?.toDoubleOrNull() ?: return null
        if (amount <= 0) return null
        if (outgoingWords.any { it in lower }) return null
        if (ignoreWords.any { it in lower }) return null

        val failed = failWords.any { it in lower }
        if (!failed && creditWords.none { it in lower }) return null

        // Look for the payer in the title first (cleanest), then in the body
        val payer = listOf(title.trim(), text.replace('\n', ' ').trim()).firstNotNullOfOrNull { part ->
            payerRx.firstNotNullOfOrNull { it.find(part)?.groupValues?.get(1)?.trim() }
        }?.takeIf { it.length in 2..40 && !it.contains('₹') && !it.lowercase().startsWith("payment") }
        return Parsed(amount, payer, if (failed) FAILED else SUCCESS)
    }
}

/**
 * Stops double alerts when the same app re-posts / updates one notification within a few seconds.
 * (App alert vs late bank SMS is matched in the database instead – see PaymentListenerService.)
 */
object DuplicateGuard {
    private data class Seen(val app: String, val amount: Double, val payer: String?, val time: Long)
    private val recent = ArrayDeque<Seen>()
    private const val SAME_WINDOW = 3_000L

    @Synchronized
    fun isDuplicate(app: String, amount: Double, payer: String?, time: Long): Boolean {
        while (recent.isNotEmpty() && time - recent.first().time > 60_000L) recent.removeFirst()
        val dup = recent.any { it.amount == amount && it.app == app && it.payer == payer && abs(time - it.time) < SAME_WINDOW }
        if (!dup) recent.addLast(Seen(app, amount, payer, time))
        return dup
    }
}

/**
 * Makes the payer text safe to read out loud (Plus plan).
 * "RAMESH KUMAR" → "Ramesh Kumar". Phone numbers, UPI IDs and words like "UPI user" → null (only the amount is said).
 */
object PayerName {
    private val bad = Regex("""\b(upi|bank|a/c|account|xx+|unknown|user|customer|merchant|paytm|phonepe|gpay|google|bhim|wallet|ref|txn)\b""",
        RegexOption.IGNORE_CASE)

    fun clean(raw: String?): String? {
        val s = raw?.trim()?.trimEnd('.', ',') ?: return null
        if (s.length < 2 || s.length > 40) return null
        if (s.any { it.isDigit() || it == '@' || it == '₹' }) return null
        if (!s.all { it.isLetter() || it == ' ' || it == '.' || it == '\'' }) return null
        if (bad.containsMatchIn(s)) return null
        return s.split(Regex("\\s+")).filter { it.isNotBlank() }.take(3)
            .joinToString(" ") { w -> w.lowercase().replaceFirstChar { it.uppercase() } }
    }
}
