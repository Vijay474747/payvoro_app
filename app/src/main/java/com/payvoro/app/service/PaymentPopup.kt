package com.payvoro.app.service

import android.content.Context
import com.payvoro.app.AppState
import com.payvoro.app.PayvoroApp
import com.payvoro.app.data.FAILED
import com.payvoro.app.data.Payment
import com.payvoro.app.data.SUCCESS
import com.payvoro.app.ui.PaymentAlertActivity
import com.payvoro.app.ui.rupees

/**
 * Shows a payment on screen. Two parts:
 *
 *  1. Small pop-up = normal phone notification (heads-up at the top). Always posted, so every
 *     payment is also in the notification shade.
 *  2. Big pop-up = full-screen green / red Payvoro screen ([PaymentAlertActivity]).
 *     Shows over other apps and over the lock screen, and turns the screen on.
 *     Android lets an app open a screen from the background only if the merchant allowed
 *     "Display over other apps". Without it, the big pop-up shows only while Payvoro is open.
 *
 * Call on the main thread.
 */
object PaymentPopup {
    const val TEST_ID = 999_999L

    fun show(ctx: Context, p: Payment, bigPopup: Boolean) {
        if (!NotificationHelper.show(ctx, p)) {
            EventLog.add(ctx, "Small pop-up blocked – allow Notifications for Payvoro")
        } else if (!NotificationHelper.headsUpAllowed(ctx)) {
            EventLog.add(ctx, "Small pop-up is silent – Payvoro 'Payment alerts' notification style was changed in phone Settings")
        }
        if (!bigPopup) return

        val appOpen = AppState.isAppInForeground()
        if (!appOpen && !Perms.canOverlay(ctx)) {
            EventLog.add(ctx, "Big pop-up not shown – allow 'Display over other apps' for Payvoro")
            return
        }
        try {
            ctx.startActivity(PaymentAlertActivity.intent(ctx, p))
            EventLog.add(ctx, "Big pop-up opened for ${rupees(p.amount)}")
        } catch (e: Exception) {
            EventLog.add(ctx, "Big pop-up failed: ${e.javaClass.simpleName} ${e.message.orEmpty()}")
        }
    }

    /** "Test Pop-up" button: same path as a real payment, but nothing is saved. */
    fun test(ctx: Context, success: Boolean) {
        val app = ctx.applicationContext as PayvoroApp
        val p = Payment(
            id = TEST_ID, amount = 100.0, payer = "Test Customer", app = "gpay",
            status = if (success) SUCCESS else FAILED, rawText = "", timestamp = System.currentTimeMillis(),
            dedupeKey = "test",
        )
        EventLog.add(app, "Test pop-up: ${if (success) "received" else "failed"} ₹100")
        if (Perms.mediaVolumeZero(app)) EventLog.add(app, "Media volume is 0 – the voice cannot be heard")
        if (success) app.announcer.announce(p.amount) else app.announcer.announceFailed(p.amount)
        show(app, p, bigPopup = true)
    }
}
