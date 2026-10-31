package com.payvoro.app

import android.app.Application
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ProcessLifecycleOwner
import com.payvoro.app.data.Payment
import com.payvoro.app.service.NotificationHelper
import com.payvoro.app.service.SoundAnnouncer
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow

class PayvoroApp : Application() {
    lateinit var announcer: SoundAnnouncer
        private set

    override fun onCreate() {
        super.onCreate()
        announcer = SoundAnnouncer(this)
        NotificationHelper.createChannel(this)
    }
}

/** Small shared state between the listener service and the UI. */
object AppState {
    val listenerConnected = MutableStateFlow(false)
    val events = MutableSharedFlow<Payment>(extraBufferCapacity = 8)

    /** Call on the main thread. */
    fun isAppInForeground(): Boolean =
        ProcessLifecycleOwner.get().lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)
}
