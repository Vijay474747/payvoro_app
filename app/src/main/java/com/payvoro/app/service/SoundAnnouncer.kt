package com.payvoro.app.service

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import com.payvoro.app.data.Prefs
import java.util.Locale
import java.util.UUID

/**
 * The "sound box": a short beep, then the amount spoken.
 *  - Basic: Tamil (default) or English.            "100 ரூபாய் பெறப்பட்டது"
 *  - Plus:  also Hindi, and the customer's name.   "ரமேஷ் அவர்களிடமிருந்து 100 ரூபாய் பெறப்பட்டது"
 */
class SoundAnnouncer(context: Context) : TextToSpeech.OnInitListener {
    private val ctx = context.applicationContext
    private val prefs = Prefs(ctx)
    private val tts = TextToSpeech(ctx, this)
    private val pending = mutableListOf<String>()

    var ready = false
        private set

    override fun onInit(status: Int) {
        ready = status == TextToSpeech.SUCCESS
        if (!ready) return
        tts.setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)          // follows media volume
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build()
        )
        applyLanguage()
        pending.forEach { speak(it) }
        pending.clear()
    }

    /** Returns false if the phone has no voice data for the chosen language (falls back to English). */
    fun applyLanguage(): Boolean {
        if (!ready) return true
        val wanted = when (lang()) {
            "ta" -> Locale("ta", "IN")
            "hi" -> Locale("hi", "IN")
            else -> Locale("en", "IN")
        }
        val r = tts.setLanguage(wanted)
        if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) {
            tts.setLanguage(Locale("en", "IN"))
            return false
        }
        return true
    }

    /** Tamil and English for every plan. Hindi is a Plus feature (Basic falls back to Tamil). */
    private fun lang() = prefs.language.let { if (it == "hi" && !prefs.isPlus()) "ta" else it }

    /** payer is said only on the Plus plan, and only if it is a real name. */
    fun announce(amount: Double, payer: String? = null) =
        speak(receivedText(amount, if (prefs.isPlus()) PayerName.clean(payer) else null))
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

    private fun speak(msg: String) {
        if (!prefs.soundOn) return
        if (!ready) { pending += msg; return }
        runCatching {
            val tone = ToneGenerator(AudioManager.STREAM_MUSIC, 90)
            tone.startTone(ToneGenerator.TONE_PROP_BEEP2, 250)
            Handler(Looper.getMainLooper()).postDelayed({ tone.release() }, 500)
        }
        tts.playSilentUtterance(350, TextToSpeech.QUEUE_ADD, null)   // let the beep finish
        tts.speak(msg, TextToSpeech.QUEUE_ADD, null, UUID.randomUUID().toString())
    }
}
