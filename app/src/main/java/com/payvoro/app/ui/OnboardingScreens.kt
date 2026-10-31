package com.payvoro.app.ui

import android.Manifest
import android.content.Intent
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.payvoro.app.data.Prefs
import com.payvoro.app.service.Perms
import kotlinx.coroutines.delay

/**
 * Where the merchant must go next:
 * Google login → shop setup → plan + UPI AutoPay → permissions → Home.
 * Home opens only after AutoPay is set (or a plan is already running).
 */
fun nextRoute(ctx: android.content.Context): String {
    val p = Prefs(ctx)
    return when {
        !p.loggedIn -> "login"
        !p.shopReady -> "setup"
        p.needsPlan -> "plans_first"
        !Perms.listenerEnabled(ctx) -> "permissions"
        else -> "home"
    }
}

/** 1. Splash */
@Composable
fun SplashScreen(onNext: (String) -> Unit) {
    val ctx = LocalContext.current
    LaunchedEffect(Unit) {
        delay(1500)
        onNext(nextRoute(ctx))
    }
    Box(
        Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.White, Color(0xFFDCD3FF)))),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            PayvoroLogo(110.dp)
            Spacer(Modifier.height(20.dp))
            Text("Payvoro", fontSize = 44.sp, fontWeight = FontWeight.ExtraBold, color = PurpleDark)
            Text("Payment Soundbox", fontSize = 16.sp, color = TextGray)
            Spacer(Modifier.height(24.dp))
            Text("Every Payment\na Notification", textAlign = TextAlign.Center, fontSize = 18.sp)
            Spacer(Modifier.height(60.dp))
            Icon(Icons.Filled.Speaker, null, tint = PurpleDark, modifier = Modifier.size(110.dp))
            Spacer(Modifier.height(40.dp))
            Text("Made for Small Businesses", color = TextGray, fontSize = 13.sp)
        }
    }
}

/** 2. Permission setup */
@Composable
fun PermissionScreen(onDone: () -> Unit) {
    val ctx = LocalContext.current
    var tick by remember { mutableIntStateOf(0) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { tick++ }   // re-check when user comes back from Settings
    val listenerOn = remember(tick) { Perms.listenerEnabled(ctx) }
    val notifOn = remember(tick) { Perms.notificationsAllowed(ctx) }
    val batteryOn = remember(tick) { Perms.batteryIgnored(ctx) }
    val notifLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { tick++ }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            TextButton(onClick = onDone) { Text("Skip") }
        }
        Text("App Permissions", fontSize = 24.sp, fontWeight = FontWeight.Bold, modifier = Modifier.align(Alignment.CenterHorizontally))
        Text("Enable permissions for smooth payment detection", color = TextGray, textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().padding(top = 4.dp, bottom = 20.dp))

        PermissionCard(Icons.Filled.NotificationsActive, "Notification Access", "To detect UPI payments from apps",
            "Required", listenerOn, "Enable") {
            ctx.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        }
        PermissionCard(Icons.Filled.Notifications, "Notifications", "For payment alerts and sound",
            "Recommended", notifOn, "Allow") {
            if (Build.VERSION.SDK_INT >= 33) notifLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        PermissionCard(Icons.Filled.BatteryChargingFull, "Battery Optimization", "Keep app running in background",
            "Recommended", batteryOn, "Allow") {
            ctx.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        }

        Text(
            "Payvoro only reads notifications from the payment apps you turn on. All other notifications are ignored. " +
                "Payvoro never touches your money.\n\n" +
                "Notification Access greyed out? Open App info → ⋮ menu → \"Allow restricted settings\", then try again.",
            color = TextGray, fontSize = 12.sp, modifier = Modifier.padding(vertical = 16.dp)
        )
        Button(
            onClick = onDone, enabled = listenerOn,
            modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(14.dp)
        ) { Text("Continue to Dashboard", fontSize = 16.sp) }
    }
}

@Composable
private fun PermissionCard(
    icon: ImageVector, title: String, desc: String, tag: String,
    granted: Boolean, button: String, onClick: () -> Unit,
) {
    WhiteCard(Modifier.fillMaxWidth().padding(bottom = 12.dp)) {
        Row(verticalAlignment = Alignment.Top) {
            Box(Modifier.size(44.dp).clip(CircleShape).background(PurpleLight), contentAlignment = Alignment.Center) {
                Icon(icon, null, tint = Purple)
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(title, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                    StatusChip(tag == "Recommended" || granted, tag)
                }
                Text(desc, color = TextGray, fontSize = 12.sp)
                Spacer(Modifier.height(8.dp))
                if (granted) Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.CheckCircle, null, tint = Green, modifier = Modifier.size(18.dp))
                    Text("  Done", color = Green, fontWeight = FontWeight.SemiBold)
                } else Button(onClick = onClick, modifier = Modifier.align(Alignment.End)) { Text(button) }
            }
        }
    }
}
