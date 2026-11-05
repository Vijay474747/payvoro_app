package com.payvoro.app.service

import android.app.Notification
import android.content.ComponentName
import android.os.Bundle
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import com.payvoro.app.AppState
import com.payvoro.app.PayvoroApp
import com.payvoro.app.data.*
import com.payvoro.app.ui.rupees
import kotlinx.coroutines.*

/**
 * Android calls this for every notification on the phone. Payvoro decides what is a REAL payment:
 *
 *  1. UPI app alert (GPay, PhonePe, Paytm, BHIM… and apps the merchant trusted)
 *     → main proof. Android tells us which app posted it, and no other app can post as GPay.
 *     → instant voice.
 *  2. Bank SMS (via the SMS app's notification)
 *     → only from bank sender IDs, never phone numbers or promotional (-P) senders,
 *       only real credits that mention the shop's account.
 *     → if it matches an earlier app alert: silently mark "Bank confirmed ✓✓" (late SMS never speaks twice).
 *  3. Anything else that looks like a payment from an unknown app/sender
 *     → NOT announced. Shown in "UPI App Selection" so the merchant can trust it once.
 */
class PaymentListenerService : NotificationListenerService() {
    // An error in one payment must never stop the listener (or crash the app).
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO + CoroutineExceptionHandler { _, e ->
        EventLog.add(applicationContext, "Error while saving a payment: ${e.javaClass.simpleName} ${e.message.orEmpty()}")
    })

    companion object {
        private const val STALE_MS = 10 * 60_000L          // app alerts older than this are re-posts (after reboot etc.)
        private const val BANK_MATCH_MS = 6 * 3_600_000L   // a late bank SMS can confirm an app alert up to 6 h old
        private const val BANK_FIRST_MS = 30 * 60_000L     // app alert arriving after a bank SMS
    }

    override fun onListenerConnected() {
        AppState.listenerConnected.value = true
        EventLog.add(this, "Listener connected – reading payment notifications")
    }

    override fun onListenerDisconnected() {
        AppState.listenerConnected.value = false
        EventLog.add(this, "Listener disconnected by Android – asking to reconnect")
        runCatching { requestRebind(ComponentName(this, PaymentListenerService::class.java)) }
    }

    override fun onDestroy() { scope.cancel(); super.onDestroy() }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName == packageName) return
        try {
            onPosted(sbn)
        } catch (e: Throwable) {
            EventLog.add(this, "Error reading a notification from ${sbn.packageName}: ${e.javaClass.simpleName} ${e.message.orEmpty()}")
        }
    }

    private fun onPosted(sbn: StatusBarNotification) {
        val prefs = Prefs(this)
        val n = sbn.notification ?: return
        if (n.flags and Notification.FLAG_GROUP_SUMMARY != 0) return
        val extras = n.extras ?: return

        val app = UpiApps.forPackage(sbn.packageName) ?: prefs.customAppFor(sbn.packageName)
        // Only payment apps are written to the log (never the merchant's chats or personal SMS).
        val name = app?.let { UpiApps.name(it.id) }
        if (!prefs.loggedIn) { if (app != null && app.id != "bank") EventLog.add(this, "$name alert ignored – not logged in"); return }
        if (!prefs.soundBoxActive) { if (app != null && app.id != "bank") EventLog.add(this, "$name alert ignored – Sound Box is paused on Home"); return }

        when {
            app == null -> learnUnknownApp(sbn, extras, prefs)
            app.id == "bank" -> if (prefs.isAppEnabled("bank")) handleBankSms(sbn, extras, prefs)
            else -> {
                if (!app.id.startsWith("other:") && !prefs.isAppEnabled(app.id)) {
                    EventLog.add(this, "$name alert ignored – $name is OFF in UPI App Selection"); return
                }
                val shownAt = if (n.`when` > 0) n.`when` else sbn.postTime
                if (System.currentTimeMillis() - shownAt > STALE_MS) {
                    EventLog.add(this, "$name alert ignored – old notification shown again"); return
                }
                handleUpiApp(app.id, sbn, extras, prefs)
            }
        }
    }

    // ---------------- 1. UPI app alerts ----------------
    private fun handleUpiApp(appId: String, sbn: StatusBarNotification, extras: Bundle, prefs: Prefs) {
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val text = bodyText(extras)
        val name = UpiApps.name(appId)
        val parsed = NotificationParser.parse(title, text)
        if (parsed == null) {
            EventLog.add(this, "$name: not a payment text: \"$title | $text\"".take(160)); return
        }
        if (DuplicateGuard.isDuplicate(appId, parsed.amount, parsed.payer, sbn.postTime)) {
            EventLog.add(this, "$name: same alert again – ignored ${rupees(parsed.amount)}"); return
        }
        val utr = BankSmsFilter.extractUtr("$title $text")

        scope.launch {
            val dao = AppDatabase.get(this@PaymentListenerService).payments()
            val sameUtr = utr?.let { dao.findByUtr(it) }
            if (sameUtr != null && sameUtr.source == SOURCE_APP) {                   // already have it
                EventLog.add(this@PaymentListenerService, "$name: same UPI ref already saved – ignored"); return@launch
            }

            // Did the bank SMS arrive first? Then upgrade that record instead of adding a second one.
            val bankFirst = sameUtr
                ?: if (parsed.status == SUCCESS) dao.findBankOnly(parsed.amount, sbn.postTime - BANK_FIRST_MS) else null
            val saved: Payment
            val alreadySpoken: Boolean
            if (bankFirst != null) {
                dao.upgradeToApp(bankFirst.id, appId, parsed.payer, utr)
                saved = bankFirst.copy(source = SOURCE_APP, app = appId, payer = parsed.payer ?: bankFirst.payer)
                alreadySpoken = prefs.announceBankSms
            } else {
                val p = Payment(
                    amount = parsed.amount, payer = parsed.payer, app = appId, status = parsed.status,
                    rawText = "$title | $text".take(300), timestamp = sbn.postTime, utr = utr, source = SOURCE_APP,
                    dedupeKey = utr ?: "${sbn.packageName}|${parsed.amount}|${(title + text).hashCode()}|${sbn.postTime / 120_000}",
                )
                val id = dao.insert(p)
                if (id <= 0) { EventLog.add(this@PaymentListenerService, "$name: already saved – ignored"); return@launch }
                saved = p.copy(id = id)
                alreadySpoken = false
            }
            if (alreadySpoken) EventLog.add(this@PaymentListenerService, "$name: matched the earlier bank SMS (already spoken)")
            else alert(saved, prefs)
            BackendSync.syncPending(this@PaymentListenerService)
        }
    }

    // ---------------- 2. Bank SMS ----------------
    private fun handleBankSms(sbn: StatusBarNotification, extras: Bundle, prefs: Prefs) {
        val sender = smsSender(extras) ?: return
        val header = BankSmsFilter.parseHeader(sender) ?: return    // phone numbers, contacts → ignored
        if (header.suffix == "P") return                            // promotional SMS → ignored
        val text = bodyText(extras)
        val credit = BankSmsFilter.parseCredit(text, prefs.accountLast4) ?: return

        if (!BankSmsFilter.isTrusted(header.brand, prefs.trustedSenders())) {
            prefs.addCandidateSender(header.brand, text)            // merchant can trust it once
            EventLog.add(this, "Bank SMS ${rupees(credit.amount)} from ${header.brand} – not trusted yet (UPI App Selection)")
            return
        }

        scope.launch {
            val dao = AppDatabase.get(this@PaymentListenerService).payments()
            val sameUtr = credit.utr?.let { dao.findByUtr(it) }
            if (sameUtr != null && (sameUtr.bankConfirmed || sameUtr.source == SOURCE_BANK)) return@launch   // already have it

            // Normal case: the UPI app already announced it → just add the bank tick, no sound.
            val match = sameUtr
                ?: dao.findAppPaymentToConfirm(credit.amount, sbn.postTime - BANK_MATCH_MS, sbn.postTime + 60_000)
            if (match != null) {
                dao.confirmByBank(match.id, credit.utr)
                EventLog.add(this@PaymentListenerService, "Bank SMS ${rupees(credit.amount)} matched an earlier app alert")
                BackendSync.syncPending(this@PaymentListenerService)
                return@launch
            }

            // Bank SMS with no app alert (e.g. the QR's app is not on this phone)
            val p = Payment(
                amount = credit.amount, payer = credit.fromVpa, app = "bank", status = SUCCESS,
                rawText = text.take(300), timestamp = sbn.postTime, utr = credit.utr,
                source = SOURCE_BANK, bankConfirmed = true,
                dedupeKey = credit.utr ?: "sms|${header.brand}|${credit.amount}|${text.hashCode()}",
            )
            val id = dao.insert(p)
            if (id <= 0) return@launch
            if (prefs.announceBankSms) alert(p.copy(id = id), prefs)
            else EventLog.add(this@PaymentListenerService, "Bank SMS ${rupees(credit.amount)} saved – voice for bank SMS is off")
            BackendSync.syncPending(this@PaymentListenerService)
        }
    }

    // ---------------- 3. Unknown apps ----------------
    private fun learnUnknownApp(sbn: StatusBarNotification, extras: Bundle, prefs: Prefs) {
        // Chat / SMS style notifications (WhatsApp, other SMS apps) are never offered as "payment apps",
        // so a forwarded or fake "credited" message can't sneak past the bank SMS check.
        if (extras.containsKey(Notification.EXTRA_MESSAGES)) return
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val parsed = NotificationParser.parse(title, bodyText(extras)) ?: return
        if (parsed.status != SUCCESS) return
        val label = runCatching {
            packageManager.getApplicationLabel(packageManager.getApplicationInfo(sbn.packageName, 0)).toString()
        }.getOrDefault(sbn.packageName)
        if (prefs.candidateApps().none { it.first == sbn.packageName })
            EventLog.add(this, "New payment app seen: $label – trust it in UPI App Selection")
        prefs.addCandidateApp(sbn.packageName, label)
    }

    // ---------------- helpers ----------------
    private suspend fun alert(p: Payment, prefs: Prefs) = withContext(Dispatchers.Main) {
        // Payment is always saved. Voice + big pop-up only while the plan (+3 grace days) is valid.
        val planOk = prefs.canAnnounce()
        val announcer = (application as PayvoroApp).announcer
        val what = "Saved ${rupees(p.amount)} from ${UpiApps.name(p.app)}"
        when {
            !planOk -> EventLog.add(this@PaymentListenerService, "$what – NO voice: no active plan")
            !prefs.soundOn -> EventLog.add(this@PaymentListenerService, "$what – NO voice: Voice alert is OFF in Profile")
            else -> {
                EventLog.add(this@PaymentListenerService, "$what – speaking" + if (announcer.ready) "" else " (voice engine starting)")
                if (Perms.mediaVolumeZero(this@PaymentListenerService))
                    EventLog.add(this@PaymentListenerService, "Media volume is 0 – the voice cannot be heard")
                if (p.status == SUCCESS) announcer.announce(p.amount) else announcer.announceFailed(p.amount)
            }
        }
        PaymentPopup.show(this@PaymentListenerService, p, bigPopup = planOk)
    }

    /** Latest message text. SMS apps use MessagingStyle, so read the last message first. */
    private fun bodyText(extras: Bundle): String {
        val msgs = extras.getParcelableArray(Notification.EXTRA_MESSAGES)
        val last = (msgs?.lastOrNull() as? Bundle)?.getCharSequence("text")?.toString()
        return last ?: (extras.getCharSequence(Notification.EXTRA_BIG_TEXT)
            ?: extras.getCharSequence(Notification.EXTRA_TEXT))?.toString().orEmpty()
    }

    private fun smsSender(extras: Bundle): String? =
        extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()?.takeIf { it.isNotBlank() }
            ?: extras.getCharSequence(Notification.EXTRA_CONVERSATION_TITLE)?.toString()
}
