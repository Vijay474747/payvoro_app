package com.payvoro.app.service

import android.Manifest
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
import android.os.PowerManager
import android.service.notification.NotificationListenerService
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.payvoro.app.data.AppDatabase
import com.payvoro.app.data.Payment
import com.payvoro.app.data.Prefs
import com.payvoro.app.data.SUCCESS
import com.payvoro.app.data.UpiApps
import com.payvoro.app.ui.MainActivity
import com.payvoro.app.ui.rupees
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

object NotificationHelper {
    private const val CHANNEL = "payments"

    fun createChannel(ctx: Context) {
        if (Build.VERSION.SDK_INT < 26) return      // Android 7 has no channels – nothing to create
        val ch = NotificationChannel(CHANNEL, "Payment alerts", NotificationManager.IMPORTANCE_HIGH)
        ch.setSound(null, null)      // the voice alert is the sound
        ctx.getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
    }

    fun show(ctx: Context, p: Payment) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        val open = PendingIntent.getActivity(
            ctx, 0,
            Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val ok = p.status == SUCCESS
        val n = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(if (ok) "${rupees(p.amount)} received" else "${rupees(p.amount)} payment failed")
            .setContentText(
                if (!Prefs(ctx).canAnnounce()) "Plan expired – voice is off. Open Payvoro to renew."
                else listOfNotNull(p.payer, UpiApps.name(p.app)).joinToString(" • ")
            )
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(ctx).notify(p.id.toInt(), n)
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

    fun rebindListener(ctx: Context) = NotificationListenerService.requestRebind(
        ComponentName(ctx, PaymentListenerService::class.java)
    )
}
