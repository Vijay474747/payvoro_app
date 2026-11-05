package com.payvoro.app.service

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Small log of what Payvoro did with each payment notification, and why.
 * Shown on the Live Status screen, so the merchant (or you, on a support call) can see
 * "Saved ₹10 – speaking" or "Not a payment text: …" without a computer.
 * Stays on this phone only. Keeps the last [MAX] lines.
 */
object EventLog {
    private const val MAX = 40
    private const val KEY = "lines"
    val lines = MutableStateFlow<List<String>>(emptyList())
    @Volatile private var loaded = false

    private fun sp(ctx: Context) = ctx.applicationContext.getSharedPreferences("payvoro_log", Context.MODE_PRIVATE)

    @Synchronized
    fun load(ctx: Context): List<String> {
        if (!loaded) {
            lines.value = sp(ctx).getString(KEY, "").orEmpty().split('\n').filter { it.isNotBlank() }
            loaded = true
        }
        return lines.value
    }

    @Synchronized
    fun add(ctx: Context, msg: String) {
        val time = SimpleDateFormat("dd MMM hh:mm:ss a", Locale.ENGLISH).format(Date())
        val line = "$time  ${msg.replace('\n', ' ').take(160)}"
        val next = (listOf(line) + load(ctx)).take(MAX)
        lines.value = next
        sp(ctx).edit().putString(KEY, next.joinToString("\n")).apply()
        android.util.Log.i("Payvoro", msg)
    }

    @Synchronized
    fun clear(ctx: Context) {
        lines.value = emptyList()
        loaded = true
        sp(ctx).edit().remove(KEY).apply()
    }
}
