package com.payvoro.app.service

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.media.AudioManager
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings
import android.service.notification.NotificationListenerService
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.payvoro.app.R
import com.payvoro.app.data.Payment
import com.payvoro.app.data.Prefs
import com.payvoro.app.data.SUCCESS
import com.payvoro.app.data.UpiApps
import com.payvoro.app.ui.MainActivity
import com.payvoro.app.ui.rupees
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

object NotificationHelper {
    /**
     * New channel ID (v1.0.2). Android never lets an app raise the importance of an existing channel,
     * so phones that got the old "payments" channel at low importance never showed a pop-up.
     */
    private const val CHANNEL = "payment_alerts_v2"
    private const val OLD_CHANNEL = "payments"

    fun createChannel(ctx: Context) {
        if (Build.VERSION.SDK_INT < 26) return      // Android 7 has no channels – nothing to create
        val nm = ctx.getSystemService(NotificationManager::class.java)
        runCatching { nm.deleteNotificationChannel(OLD_CHANNEL) }
        val ch = NotificationChannel(CHANNEL, "Payment alerts", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "A pop-up for every payment"
            setSound(null, null)            // the voice alert is the sound
            enableVibration(false)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        }
        nm.createNotificationChannel(ch)
    }

    /** False if the merchant lowered "Payment alerts" in phone Settings (then no pop-up at the top). */
    fun headsUpAllowed(ctx: Context): Boolean {
        if (Build.VERSION.SDK_INT < 26) return true
        val ch = ctx.getSystemService(NotificationManager::class.java).getNotificationChannel(CHANNEL) ?: return true
        return ch.importance >= NotificationManager.IMPORTANCE_HIGH
    }

    /** Posts the small pop-up. Returns false if notifications are blocked for Payvoro. */
    fun show(ctx: Context, p: Payment): Boolean {
        if (!Perms.notificationsAllowed(ctx) || !NotificationManagerCompat.from(ctx).areNotificationsEnabled()) return false
        val open = PendingIntent.getActivity(
            ctx, 0,
            Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val ok = p.status == SUCCESS
        val b = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_payvoro)
            .setColor(if (ok) 0xFF16A34A.toInt() else 0xFFDC2626.toInt())
            .setContentTitle(if (ok) "${rupees(p.amount)} received" else "${rupees(p.amount)} payment failed")
            .setContentText(
                if (p.id != PaymentPopup.TEST_ID && !Prefs(ctx).canAnnounce()) "Plan expired – voice is off. Open Payvoro to renew."
                else listOfNotNull(p.payer, UpiApps.name(p.app)).joinToString(" • ")
            )
            .setWhen(p.timestamp).setShowWhen(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setContentIntent(open)
            .setAutoCancel(true)
        // Android 7 shows a pop-up at the top only if the notification vibrates or makes a sound.
        if (Build.VERSION.SDK_INT < 26) b.setVibrate(longArrayOf(0, 150))
        return runCatching { NotificationManagerCompat.from(ctx).notify(p.id.toInt(), b.build()); true }.getOrDefault(false)
    }
}

/**
 * Server sync. Customer payments are NOT sent to the server any more (Razorpay review):
 * they stay only on this phone. This now only refreshes the merchant's plan from the server.
 */
object BackendSync {
    private val mutex = Mutex()

    suspend fun syncPending(ctx: Context): Boolean = mutex.withLock {
        if (!Prefs(ctx).loggedIn) return false
        // Only the plan is fetched (renewals reach the phone). No payment data leaves the phone.
        Api.refreshMe(ctx).isSuccess
    }

    fun ping(ctx: Context): Boolean = Api.refreshMe(ctx).isSuccess
}

object Perms {
    fun listenerEnabled(ctx: Context) =
        NotificationManagerCompat.getEnabledListenerPackages(ctx).contains(ctx.packageName)

    fun notificationsAllowed(ctx: Context) = Build.VERSION.SDK_INT < 33 ||
        ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    fun batteryIgnored(ctx: Context) =
        ctx.getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(ctx.packageName)

    fun hasInternet(ctx: Context): Boolean {
        val cm = ctx.getSystemService(ConnectivityManager::class.java)
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    fun isInstalled(ctx: Context, packages: List<String>) = packages.any {
        runCatching { ctx.packageManager.getPackageInfo(it, 0); true }.getOrDefault(false)
    }

    fun rebindListener(ctx: Context) {
        if (listenerEnabled(ctx)) runCatching {
            NotificationListenerService.requestRebind(ComponentName(ctx, PaymentListenerService::class.java))
        }
    }

    /** "Display over other apps": lets the big payment pop-up open when Payvoro is closed. */
    fun canOverlay(ctx: Context) = Settings.canDrawOverlays(ctx)

    fun overlaySettings(ctx: Context) =
        Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:${ctx.packageName}"))

    /** The voice uses media volume. */
    fun mediaVolumeZero(ctx: Context) =
        ctx.getSystemService(AudioManager::class.java).getStreamVolume(AudioManager.STREAM_MUSIC) == 0

    fun isXiaomi() = Build.MANUFACTURER.equals("Xiaomi", ignoreCase = true) ||
        Build.BRAND.lowercase().let { it == "redmi" || it == "poco" || it == "xiaomi" }

    /** Xiaomi / Redmi / POCO hide "Show on lock screen" and "Pop-up windows from background" here. */
    fun xiaomiPermissions(ctx: Context): Intent =
        Intent("miui.intent.action.APP_PERM_EDITOR")
            .setClassName("com.miui.securitycenter", "com.miui.permcenter.permissions.PermissionsEditorActivity")
            .putExtra("extra_pkgname", ctx.packageName)

    fun appInfo(ctx: Context) =
        Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${ctx.packageName}"))
}
