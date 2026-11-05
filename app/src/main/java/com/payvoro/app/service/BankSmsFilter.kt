package com.payvoro.app.service

/**
 * Decides if a bank SMS is a REAL money-received message for this shop.
 * Pure Kotlin – unit tested in BankSmsFilterTest.
 *
 * Layers of checks:
 *  1. Sender must be a registered business header (e.g. "JD-HDFCBK-T"), never a phone number.
 *  2. "-P" (promotional) headers are dropped. TRAI adds -P/-S/-T/-G to every header since May 2025.
 *  3. Sender must be a known bank, or one the merchant trusted once in the app.
 *  4. No spam signs: links, loan, offer, cashback, KYC, "will be credited", OTP …
 *  5. Must say credited / received / deposited, and that must not come after a debit word.
 *  6. Must mention an account (A/c XX1234). If the merchant saved the last 4 digits, they must match.
 */
object BankSmsFilter {
    data class Header(val brand: String, val suffix: String?)
    data class BankCredit(val amount: Double, val utr: String?, val accountTail: String, val fromVpa: String?)

    /**
     * Common bank sender codes (the middle part of "JD-HDFCBK-T").
     * Not complete – the app shows any new bank-looking sender so the merchant can trust it once
     * (for example their Tamil Nadu Grama Bank header).
     */
    val KNOWN_BANKS = setOf(
        "HDFCBK", "ICICIB", "ICICIT", "SBIUPI", "SBIINB", "SBIPSG", "CBSSBI", "ATMSBI",
        "AXISBK", "KOTAKB", "IDFCFB", "INDUSB", "YESBNK", "PNBSMS", "BOIIND", "BOBTXN", "BOBSMS",
        "UNIONB", "CANBNK", "INDBNK", "IOBCHN", "CENTBK", "UCOBNK", "IDBIBK", "FEDBNK", "SIBSMS",
        "KVBANK", "CUBANK", "TMBANK", "DBSBNK", "AUBANK", "PAYTMB", "AIRBNK", "IPBMSG",
    )

    private val headerRx = Regex("""^(?:[A-Z]{2}-)?([A-Z0-9]{3,9})(?:-([PSTG]))?$""")

    /** Returns null for phone numbers, contact names with spaces, short codes … */
    fun parseHeader(sender: String): Header? {
        val s = sender.trim().uppercase()
        if (s.isEmpty() || s.any { it.isWhitespace() } || s.startsWith("+")) return null
        if (s.count { it.isDigit() } >= 5) return null                 // phone numbers / numeric short codes
        val m = headerRx.matchEntire(s) ?: return null
        val brand = m.groupValues[1]
        if (!s.contains('-') && brand.length != 6) return null          // bare names must look like a 6-letter header
        if (brand.all { it.isDigit() }) return null
        return Header(brand, m.groupValues[2].ifBlank { null })
    }

    fun isTrusted(brand: String, custom: Set<String>) = brand in KNOWN_BANKS || brand in custom

    private val amountRx = Regex("""(?:₹|\brs\.?|\binr)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)""", RegexOption.IGNORE_CASE)
    private val creditByRx = Regex("""credited\s+(?:by|with|for)\s+([0-9][0-9,]*(?:\.[0-9]{1,2})?)""", RegexOption.IGNORE_CASE)
    private val creditRx = Regex("""\b(credited|deposited|received)\b""", RegexOption.IGNORE_CASE)
    private val debitRx = Regex("""\b(debited|withdrawn|spent|sent|purchase|paid to)\b""", RegexOption.IGNORE_CASE)
    private val accountRx = Regex("""(?:a/c|acct|account|\bac)\.?\s*(?:no\.?|number)?\s*[:\-]?\s*[x*.]*\s*(\d{3,6})(?!\d)""", RegexOption.IGNORE_CASE)
    private val vpaRx = Regex("""[A-Za-z0-9.\-_]{2,64}@[A-Za-z][A-Za-z0-9]{1,30}""")
    private val utrRx = Regex("""(?:utr|upi\s*ref(?:\s*no)?|ref(?:erence)?\s*(?:no|number|id)?|rrn|upi)\s*[:.\-#]?\s*(?:no\.?\s*)?(\d{12})(?!\d)""", RegexOption.IGNORE_CASE)
    private val any12Rx = Regex("""(?<!\d)(\d{12})(?!\d)""")

    // Whole words only, and never inside a UPI ID: "emi" in "hemitha@okaxis", "free" in "freedom.k@oksbi"
    // used to drop real credits.
    private val spamRx = Regex(
        """https?://|www\.|bit\.ly|\b(?:click|apply|loans?|lottery|won|winner|prize|kyc|cashback|rewards?|offers?|claim|""" +
            """pre-?approved|otp|request(?:ed)?|emis?|free)\b|\b(?:will|to|shall) be credited\b""",
        RegexOption.IGNORE_CASE
    )

    /** UPI reference / UTR: 12 digits. Used to spot the same payment twice. */
    fun extractUtr(text: String): String? =
        utrRx.find(text)?.groupValues?.get(1) ?: any12Rx.find(text)?.groupValues?.get(1)

    fun parseCredit(text: String, accountLast4: String?): BankCredit? {
        val t = text.replace('\n', ' ').trim()
        if (spamRx.containsMatchIn(vpaRx.replace(t, " "))) return null      // UPI IDs are removed before the spam check
        val credit = creditRx.find(t) ?: return null
        val debit = debitRx.find(t)
        if (debit != null && debit.range.first < credit.range.first) return null
        val acct = accountRx.find(t) ?: return null
        val tail = acct.groupValues[1]
        val last4 = accountLast4?.filter { it.isDigit() }.orEmpty()
        if (last4.isNotEmpty() && !(last4.endsWith(tail) || tail.endsWith(last4))) return null
        val amount = (amountRx.find(t) ?: creditByRx.find(t))?.groupValues?.get(1)
            ?.replace(",", "")?.toDoubleOrNull() ?: return null
        if (amount <= 0) return null
        return BankCredit(amount, extractUtr(t), tail, vpaRx.find(t)?.value)
    }
}
