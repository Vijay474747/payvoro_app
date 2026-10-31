package com.payvoro.app.ui

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.navigation.NavController
import com.payvoro.app.AppState
import com.payvoro.app.BuildConfig
import com.payvoro.app.PayvoroApp
import com.payvoro.app.data.AppDatabase
import com.payvoro.app.data.Prefs
import com.payvoro.app.data.UpiApps
import com.payvoro.app.service.Api
import com.payvoro.app.service.BackendSync
import com.payvoro.app.service.Perms
import com.payvoro.app.service.UpiQrParser
import androidx.compose.material.icons.automirrored.filled.Logout
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** 10. Profile & settings */
@Composable
fun ProfileScreen(nav: NavController) {
    val ctx = LocalContext.current
    val prefs = remember { Prefs(ctx) }
    val scope = rememberCoroutineScope()
    val announcer = (ctx.applicationContext as PayvoroApp).announcer

    // Saved shop details. Changed only after tapping "Edit".
    var savedName by remember { mutableStateOf(prefs.merchantName) }
    var savedUpi by remember { mutableStateOf(prefs.upiId) }
    var editing by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf(savedName) }
    var upi by remember { mutableStateOf(savedUpi) }
    var saving by remember { mutableStateOf(false) }
    var confirmUpi by remember { mutableStateOf(false) }
    var lang by remember { mutableStateOf(prefs.language) }
    val plus = prefs.isPlus()
    var sound by remember { mutableStateOf(prefs.soundOn) }

    // Coming back from the QR scanner (Edit → scan): it saves the new UPI ID itself
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        if (prefs.upiId != savedUpi) { savedUpi = prefs.upiId; upi = savedUpi }
        if (prefs.merchantName != savedName) { savedName = prefs.merchantName; name = savedName }
    }

    fun doSave() {
        val newName = name.trim().ifBlank { "My Shop" }
        val newUpi = upi.trim()
        saving = true
        scope.launch {
            val r = withContext(Dispatchers.IO) { Api.updateMe(ctx, newName.takeIf { it.length >= 2 }, newUpi) }
            saving = false
            if (r.isSuccess || Api.demo) {
                if (newUpi != prefs.upiId) prefs.qrRaw = ""          // typed by hand → no scanned QR
                prefs.merchantName = newName; prefs.upiId = newUpi
                savedName = newName; savedUpi = newUpi
                editing = false
                Toast.makeText(ctx, "Saved", Toast.LENGTH_SHORT).show()
            } else Toast.makeText(ctx, "Not saved. ${r.exceptionOrNull()?.message}", Toast.LENGTH_LONG).show()
        }
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
        TopBar("Profile")
        WhiteCard(Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(56.dp).clip(CircleShape).background(PurpleLight), contentAlignment = Alignment.Center) {
                    Text(savedName.take(1).uppercase(), fontSize = 24.sp, fontWeight = FontWeight.Bold, color = Purple)
                }
                Spacer(Modifier.width(12.dp))
                Column {
                    Text(savedName, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                    Text(prefs.email.ifBlank { prefs.phone.takeIf { it.isNotBlank() }?.let { "+91 $it" } ?: "" },
                        color = TextGray, fontSize = 13.sp)
                }
            }
            Spacer(Modifier.height(12.dp))
            if (!editing) {
                // Saved data, shown as a card
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Bg).padding(12.dp)) {
                    Text("Shop name", color = TextGray, fontSize = 12.sp)
                    Text(savedName, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                    HorizontalDivider(Modifier.padding(vertical = 8.dp), color = PurpleLight)
                    Text("UPI ID", color = TextGray, fontSize = 12.sp)
                    Text(savedUpi.ifBlank { "Not set – tap Edit" }, fontWeight = FontWeight.SemiBold, fontSize = 16.sp,
                        color = if (savedUpi.isBlank()) Red else Color.Unspecified)
                }
                OutlinedButton(
                    onClick = { name = savedName; upi = savedUpi; editing = true },
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp)
                ) { Icon(Icons.Filled.Edit, null); Text("  Edit") }
            } else {
                OutlinedTextField(name, { name = it.take(60) }, label = { Text("Shop name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(upi, { upi = it.trim() }, label = { Text("UPI ID (e.g. shop@okaxis)") }, singleLine = true,
                    trailingIcon = { IconButton(onClick = { nav.navigate("scan") }) { Icon(Icons.Filled.QrCodeScanner, "Scan QR", tint = Purple) } },
                    modifier = Modifier.fillMaxWidth())
                Row(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedButton(onClick = { name = savedName; upi = savedUpi; editing = false }, modifier = Modifier.weight(1f)) { Text("Cancel") }
                    Button(enabled = !saving, modifier = Modifier.weight(1f), onClick = {
                        when {
                            name.trim().length < 2 -> Toast.makeText(ctx, "Enter your shop name", Toast.LENGTH_SHORT).show()
                            !UpiQrParser.isValidVpa(upi.trim()) -> Toast.makeText(ctx, "This UPI ID looks wrong", Toast.LENGTH_SHORT).show()
                            savedUpi.isNotBlank() && upi.trim() != savedUpi -> confirmUpi = true
                            else -> doSave()
                        }
                    }) { Text(if (saving) "Saving…" else "Save") }
                }
            }
        }
        if (confirmUpi) AlertDialog(
            onDismissRequest = { confirmUpi = false },
            title = { Text("Change UPI ID?") },
            text = { Text("Old: $savedUpi\nNew: ${upi.trim()}\n\nA wrong UPI ID means no voice alerts. Please check it.") },
            confirmButton = { TextButton(onClick = { confirmUpi = false; doSave() }) { Text("Yes, change") } },
            dismissButton = { TextButton(onClick = { confirmUpi = false }) { Text("Cancel") } }
        )

        // Plan card
        Text("My Plan", fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 16.dp, bottom = 8.dp))
        WhiteCard(Modifier.fillMaxWidth().clickable { nav.navigate("plans") }) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.WorkspacePremium, null, tint = Purple)
                Column(Modifier.weight(1f).padding(start = 12.dp)) {
                    Text(prefs.planLabel(), fontWeight = FontWeight.Bold)
                    Text(
                        when {
                            !prefs.planActive() -> "Expired – tap to renew"
                            prefs.hasAutopay() -> "${prefs.daysLeft()} days left · UPI AutoPay ON"
                            else -> "${prefs.daysLeft()} days left"
                        },
                        color = if (prefs.planActive()) TextGray else Red, fontSize = 13.sp
                    )
                }
                Text("Manage", color = Purple, fontWeight = FontWeight.SemiBold)
            }
        }

        Text("Sound Settings", fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 16.dp, bottom = 8.dp))
        WhiteCard(Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.AutoMirrored.Filled.VolumeUp, null, tint = Purple)
                Text("  Voice alert", modifier = Modifier.weight(1f))
                Switch(sound, { sound = it; prefs.soundOn = it })
            }
            Text("Language", color = TextGray, fontSize = 12.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                // Basic: Tamil or English. Plus: also Hindi, and the customer's name is said.
                listOf("ta" to "தமிழ்", "en" to "English", "hi" to "हिंदी").forEach { (code, label) ->
                    FilterChip(selected = lang == code, onClick = {
                        if (code == "hi" && !plus) {
                            Toast.makeText(ctx, "$label voice is in the Plus plan", Toast.LENGTH_SHORT).show()
                            nav.navigate("plans"); return@FilterChip
                        }
                        lang = code; prefs.language = code
                        if (!announcer.applyLanguage())
                            Toast.makeText(ctx, "Voice for $label not installed. Install it in phone Settings → Text-to-speech.", Toast.LENGTH_LONG).show()
                        announcer.test()
                    }, label = { Text(if (code == "hi" && !plus) "$label 🔒" else label) })
                }
            }
            Text(
                if (plus) "Plus: the customer's name is also said (when the UPI app shows it)."
                else "Upgrade to Plus to hear the customer's name.",
                color = TextGray, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp)
            )
            OutlinedButton(onClick = { announcer.test() }, modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
                Icon(Icons.AutoMirrored.Filled.VolumeUp, null); Text("  Test Sound")
            }
        }

        Spacer(Modifier.height(16.dp))
        WhiteCard(Modifier.fillMaxWidth()) {
            MenuRow(Icons.Filled.Apps, "UPI App Selection") { nav.navigate("apps") }
            MenuRow(Icons.Filled.Shield, "App Permissions") { nav.navigate("permissions_again") }
            MenuRow(Icons.Filled.MonitorHeart, "Live Status") { nav.navigate("status") }
            Row(Modifier.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.Info, null, tint = Purple)
                Text("  About Payvoro", modifier = Modifier.weight(1f))
                Text("v${BuildConfig.VERSION_NAME}", color = TextGray)
            }
        }
        var confirmLogout by remember { mutableStateOf(false) }
        OutlinedButton(
            onClick = { confirmLogout = true },
            colors = ButtonDefaults.outlinedButtonColors(contentColor = Red),
            modifier = Modifier.fillMaxWidth().padding(top = 16.dp).height(48.dp)
        ) { Icon(Icons.AutoMirrored.Filled.Logout, null); Text("  Logout") }
        if (confirmLogout) AlertDialog(
            onDismissRequest = { confirmLogout = false },
            title = { Text("Logout?") },
            text = { Text("Payment voice alerts will stop on this phone until you log in again.") },
            confirmButton = {
                TextButton(onClick = {
                    confirmLogout = false
                    scope.launch {
                        withContext(Dispatchers.IO) { Api.logout(ctx) }
                        nav.navigate("login") { popUpTo(nav.graph.id) { inclusive = true } }
                    }
                }) { Text("Logout", color = Red) }
            },
            dismissButton = { TextButton(onClick = { confirmLogout = false }) { Text("Cancel") } }
        )
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun MenuRow(icon: ImageVector, label: String, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, null, tint = Purple)
        Text("  $label", modifier = Modifier.weight(1f))
        Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null, tint = TextGray)
    }
}

/** 11. Live status – quick health check the merchant (or you, on a support call) can read */
@Composable
fun StatusScreen(onBack: () -> Unit) {
    val ctx = LocalContext.current
    val prefs = remember { Prefs(ctx) }
    val announcer = (ctx.applicationContext as PayvoroApp).announcer
    val connected by AppState.listenerConnected.collectAsState()
    val all by remember { AppDatabase.get(ctx).payments().all() }.collectAsState(initial = emptyList())
    var tick by remember { mutableIntStateOf(0) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { tick++ }

    val listenerEnabled = remember(tick) { Perms.listenerEnabled(ctx) }
    val internet = remember(tick) { Perms.hasInternet(ctx) }
    val battery = remember(tick) { Perms.batteryIgnored(ctx) }
    var server by remember { mutableStateOf<Boolean?>(null) }
    LaunchedEffect(tick) {
        server = withContext(Dispatchers.IO) { BackendSync.ping(ctx) }
    }
    val appsOn = UpiApps.all.count { prefs.isAppEnabled(it.id) }
    val running = listenerEnabled && prefs.soundBoxActive && prefs.canAnnounce()
    val last = all.firstOrNull()?.timestamp

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
        TopBar("Live Status", onBack)
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(if (running) Green else Red).padding(18.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(Icons.Filled.Headphones, null, tint = Color.White, modifier = Modifier.size(40.dp))
            Column(Modifier.weight(1f).padding(start = 12.dp)) {
                Text("Sound Box", color = Color.White.copy(alpha = 0.85f))
                Text(if (running) "Running" else "Stopped", color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Bold)
                Text(last?.let { "Last payment, ${minutesAgo(it)}" } ?: "No payments yet", color = Color.White.copy(alpha = 0.85f), fontSize = 12.sp)
            }
            Icon(if (running) Icons.Filled.CheckCircle else Icons.Filled.Error, null, tint = Color.White)
        }
        Spacer(Modifier.height(12.dp))
        WhiteCard(Modifier.fillMaxWidth()) {
            CheckRow(Icons.Filled.NotificationsActive, "Notification Listener",
                when { !listenerEnabled -> "Permission off"; connected -> "Active"; else -> "Waiting to connect" },
                listenerEnabled)
            CheckRow(Icons.Filled.Wifi, "Internet Connection", if (internet) "Connected" else "Offline (payments still announced)", internet)
            CheckRow(Icons.AutoMirrored.Filled.VolumeUp, "Audio Engine", if (announcer.ready) "Ready" else "Starting…", announcer.ready)
            CheckRow(Icons.Filled.BatteryChargingFull, "Battery Optimization", if (battery) "Unrestricted" else "May stop in background", battery)
            CheckRow(Icons.Filled.Cloud, "Backend Server",
                if (com.payvoro.app.service.Api.demo) "Demo mode (no server)" else when (server) { null -> "Checking…"; true -> "Connected"; false -> "Not reachable" }, server != false)
            CheckRow(Icons.Filled.Apps, "UPI App Monitoring", "$appsOn apps active", appsOn > 0)
            CheckRow(Icons.Filled.WorkspacePremium, "Plan",
                if (prefs.planActive()) "${prefs.planLabel()} – ${prefs.daysLeft()} days left"
                else if (prefs.canAnnounce()) "Expired – renew within 3 days" else "Expired – voice is off",
                prefs.planActive())
        }
        Row(Modifier.padding(vertical = 16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(onClick = { Perms.rebindListener(ctx); tick++ }, modifier = Modifier.weight(1f)) { Text("Recheck Status") }
            Button(onClick = { announcer.test() }, modifier = Modifier.weight(1f)) { Text("Test Sound") }
        }
    }
}

@Composable
private fun CheckRow(icon: ImageVector, title: String, sub: String, ok: Boolean) {
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, null, tint = Purple)
        Column(Modifier.weight(1f).padding(start = 12.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
            Text(sub, color = TextGray, fontSize = 12.sp)
        }
        StatusChip(ok, if (ok) "OK" else "Fix")
    }
}
