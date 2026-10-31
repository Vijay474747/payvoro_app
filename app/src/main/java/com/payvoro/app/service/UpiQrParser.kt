package com.payvoro.app.service

import java.net.URLDecoder

data class ScannedUpi(
    val vpa: String,          // UPI ID, e.g. ravistores@okaxis
    val name: String?,        // shop name printed in the QR, if any
    val raw: String,          // full original QR text (kept so we can show the bank's exact QR)
    val isUpiLink: Boolean,   // true for upi://pay?... QRs
)

/**
 * Reads the text inside a shop's existing QR sticker and finds the UPI ID.
 * Handles: upi://pay?pa=...  |  Bharat QR / EMV (000201...)  |  a plain UPI ID.
 * Pure Kotlin – unit tested in UpiQrParserTest.
 */
object UpiQrParser {
    private val vpaRx = Regex("""^[A-Za-z0-9.\-_]{2,256}@[A-Za-z][A-Za-z0-9]{1,63}$""")

    fun isValidVpa(v: String) = vpaRx.matches(v.trim())

    fun parse(text: String): ScannedUpi? {
        val s = text.trim()
        if (s.lowercase().startsWith("upi://")) {
            val params = s.substringAfter('?', "").split('&').mapNotNull { kv ->
                val i = kv.indexOf('=')
                if (i <= 0) null else kv.substring(0, i).lowercase() to decode(kv.substring(i + 1))
            }.toMap()
            val pa = params["pa"]?.trim() ?: return null
            if (!isValidVpa(pa)) return null
            return ScannedUpi(pa, params["pn"]?.trim()?.takeIf { it.isNotBlank() }, s, true)
        }
        if (s.startsWith("000201")) return parseEmv(s)
        if (isValidVpa(s)) return ScannedUpi(s, null, s, false)
        return null
    }

    /** Amount QR built on top of the shop's own QR, so bank merchant details are kept. */
    fun withAmount(scanned: ScannedUpi?, vpa: String, name: String, amount: Double?): String {
        val am = amount?.takeIf { it > 0 }?.let { String.format(java.util.Locale.US, "%.2f", it) }
        if (scanned != null && scanned.isUpiLink && scanned.vpa.equals(vpa, ignoreCase = true)) {
            if (am == null) return scanned.raw
            val base = scanned.raw.substringBefore('?')
            val rest = scanned.raw.substringAfter('?', "").split('&')
                .filter { it.isNotBlank() && !it.lowercase().startsWith("am=") }
            return base + "?" + (rest + "am=$am").joinToString("&")
        }
        if (scanned != null && !scanned.isUpiLink && am == null && scanned.vpa.equals(vpa, ignoreCase = true)
            && scanned.raw.startsWith("000201")) return scanned.raw          // show the Bharat QR as-is
        val sb = StringBuilder("upi://pay?pa=").append(encode(vpa)).append("&pn=").append(encode(name)).append("&cu=INR")
        if (am != null) sb.append("&am=").append(am)
        return sb.toString()
    }

    private fun decode(v: String) = runCatching { URLDecoder.decode(v, "UTF-8") }.getOrDefault(v)
    private fun encode(v: String) = java.net.URLEncoder.encode(v, "UTF-8").replace("+", "%20")

    /** Simple TLV reader: 2-digit tag, 2-digit length, value. */
    private fun tlv(s: String): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        var i = 0
        while (i + 4 <= s.length) {
            val tag = s.substring(i, i + 2)
            val len = s.substring(i + 2, i + 4).toIntOrNull() ?: break
            if (i + 4 + len > s.length) break
            out[tag] = s.substring(i + 4, i + 4 + len)
            i += 4 + len
        }
        return out
    }

    private fun parseEmv(s: String): ScannedUpi? {
        val top = tlv(s)
        // Merchant account info lives in tags 26–51; the UPI ID is one of the sub-values
        val vpa = (26..51).asSequence()
            .mapNotNull { top[it.toString()] }
            .flatMap { tlv(it).values.asSequence() }
            .firstOrNull { isValidVpa(it) } ?: return null
        return ScannedUpi(vpa, top["59"]?.trim()?.takeIf { it.isNotBlank() }, s, false)
    }
}
