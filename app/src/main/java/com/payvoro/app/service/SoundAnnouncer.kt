package com.payvoro.app.service

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import com.payvoro.app.data.Prefs
import java.util.Locale
import java.util.UUID

/**
 * The "sound box": a short beep, then the amount spoken.
 *  Tamil (default) or English. Only the amount is said.   "100 ரூபாய் பெறப்பட்டது"
 *  (The Plus plan with Hindi and the customer's name was removed.)
 */
class SoundAnnouncer(context: Context) {
    private val ctx = context.applicationContext
    private val prefs = Prefs(ctx)
    private val main = Handler(Looper.getMainLooper())
    private var tts: TextToSpeech? = null
    private val pending = mutableListOf<String>()
    private var starting = false
    private var failedStarts = 0
    private var lastRestart = 0L

    @Volatile var ready = false
        private set

    init { start() }

    /**
     * (Re)starts the phone's text-to-speech engine. Called at app start, and again when the engine
     * fails to start, dies (phone killed it, engine app updated) or reports an error while speaking.
     * Before v1.0.2 a dead engine meant silence until the phone was restarted.
     */
    private fun start() {
        if (starting) return
        starting = true
        ready = false
        runCatching { tts?.shutdown() }
        lateinit var engine: TextToSpeech
        engine = TextToSpeech(ctx) { status -> main.post { if (tts === engine && starting) onInit(status) } }
        tts = engine
        // Some phones never answer when the engine is broken. Try again after 15 s.
        main.postDelayed({
            if (starting && tts === engine) { starting = false; onInit(TextToSpeech.ERROR) }
        }, 15_000L)
    }

    private fun onInit(status: Int) {
        starting = false
        val engine = tts ?: return
        if (status != TextToSpeech.SUCCESS) {
            failedStarts++
            EventLog.add(ctx, "Voice engine did not start (try $failedStarts) – check phone Settings → Text-to-speech")
            main.postDelayed({ start() }, if (failedStarts < 5) 5_000L else 60_000L)
            return
        }
        failedStarts = 0
        engine.setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)          // follows media volume
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build()
        )
        engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {}
            override fun onDone(utteranceId: String?) {}
            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) { main.post { restart("voice error while speaking") } }
            override fun onError(utteranceId: String?, errorCode: Int) { main.post { restart("voice error $errorCode while speaking") } }
        })
        ready = true
        applyLanguage()
        val queued = pending.toList()
        pending.clear()
        queued.forEach { speak(it) }
    }

    /** At most once every 20 s, so a broken engine can't loop. */
    private fun restart(why: String) {
        val now = SystemClock.elapsedRealtime()
        if (now - lastRestart < 20_000L) return
        lastRestart = now
        EventLog.add(ctx, "Restarting voice engine – $why")
        start()
    }

    /** Returns false if the phone has no voice data for the chosen language (falls back to English). */
    fun applyLanguage(): Boolean {
        if (!ready) return true
        val wanted = when (lang()) {
            "ta" -> Locale("ta", "IN")
            "hi" -> Locale("hi", "IN")
            else -> Locale("en", "IN")
        }
        val engine = tts ?: return true
        val r = runCatching { engine.setLanguage(wanted) }.getOrDefault(TextToSpeech.LANG_NOT_SUPPORTED)
        if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) {
            runCatching { engine.setLanguage(Locale("en", "IN")) }
            return false
        }
        return true
    }

    /** Tamil or English. Old "hi" setting falls back to Tamil. */
    private fun lang() = prefs.language.let { if (it == "hi") "ta" else it }

    /** Only the amount is spoken. [payer] is ignored (kept so old callers still compile). */
    @Suppress("UNUSED_PARAMETER")
    fun announce(amount: Double, payer: String? = null) = speak(receivedText(amount, null))
    fun announceFailed(amount: Double) = speak(failedText(amount))
    fun test() = announce(100.0, "Ramesh")

    private fun spoken(a: Double): String =
        if (a % 1.0 == 0.0) a.toLong().toString() else String.format(Locale.US, "%.2f", a)

    private fun receivedText(a: Double, name: String?): String {
        val x = spoken(a)
        return when (lang()) {
            "ta" -> if (name != null) "$name அவர்களிடமிருந்து $x ரூபாய் பெறப்பட்டது" else "$x ரூபாய் பெறப்பட்டது"
            "hi" -> if (name != null) "$name से $x रुपये प्राप्त हुए" else "$x रुपये प्राप्त हुए"
            else -> if (name != null) "Received $x rupees from $name" else "Received $x rupees"
        }
    }

    private fun failedText(a: Double): String {
        val x = spoken(a)
        return when (lang()) {
            "ta" -> "$x ரூபாய் பணம் தோல்வியடைந்தது"
            "hi" -> "$x रुपये का भुगतान विफल रहा"
            else -> "Payment of $x rupees failed"
        }
    }

    /** Call on the main thread. */
    private fun speak(msg: String) {
        if (!prefs.soundOn) return
        val engine = tts
        if (!ready || engine == null) {
            if (pending.size < 5) pending += msg
            start()
            return
        }
        runCatching {
            val tone = ToneGenerator(AudioManager.STREAM_MUSIC, 90)
            tone.startTone(ToneGenerator.TONE_PROP_BEEP2, 250)
            main.postDelayed({ tone.release() }, 500)
        }
        engine.playSilentUtterance(350, TextToSpeech.QUEUE_ADD, null)   // let the beep finish
        val r = engine.speak(msg, TextToSpeech.QUEUE_ADD, null, UUID.randomUUID().toString())
        if (r == TextToSpeech.ERROR) {
            // Engine died in the background → restart it and say this message when it is back.
            if (pending.size < 5) pending += msg
            ready = false
            lastRestart = SystemClock.elapsedRealtime()
            EventLog.add(ctx, "Voice engine stopped – restarting it")
            start()
        }
    }
}
