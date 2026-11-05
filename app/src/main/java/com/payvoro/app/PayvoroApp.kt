package com.payvoro.app

import android.app.Application
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ProcessLifecycleOwner
import com.payvoro.app.service.EventLog
import com.payvoro.app.service.NotificationHelper
import com.payvoro.app.service.SoundAnnouncer
import kotlinx.coroutines.flow.MutableStateFlow

class PayvoroApp : Application() {
    lateinit var announcer: SoundAnnouncer
        private set

    override fun onCreate() {
        super.onCreate()
        NotificationHelper.createChannel(this)
        EventLog.load(this)
        announcer = SoundAnnouncer(this)
    }
}

/** Small shared state between the listener service and the UI. */
object AppState {
    val listenerConnected = MutableStateFlow(false)

    /** Call on the main thread. */
    fun isAppInForeground(): Boolean =
        ProcessLifecycleOwner.get().lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)
}
