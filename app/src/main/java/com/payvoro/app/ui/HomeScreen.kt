package com.payvoro.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.VolumeUp
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
import androidx.navigation.NavController
import com.payvoro.app.data.AppDatabase
import com.payvoro.app.data.Prefs
import com.payvoro.app.data.SUCCESS
import com.payvoro.app.service.Perms

/** 3. Home dashboard */
@Composable
fun HomeScreen(nav: NavController) {
    val ctx = LocalContext.current
    val prefs = remember { Prefs(ctx) }
    val all by remember { AppDatabase.get(ctx).payments().all() }.collectAsState(initial = emptyList())
    var active by remember { mutableStateOf(prefs.soundBoxActive) }
    var tick by remember { mutableIntStateOf(0) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { tick++ }
    val listenerOn = remember(tick) { Perms.listenerEnabled(ctx) }
    val overlayOn = remember(tick) { Perms.canOverlay(ctx) }

    val ok = all.filter { it.status == SUCCESS }
    val today = ok.filter { it.timestamp >= startOfDay() }
    val month = ok.filter { it.timestamp >= startOfMonth() }

    LazyColumn(Modifier.fillMaxSize()) {
        item {
            Column(
                Modifier.fillMaxWidth()
                    .background(Brush.verticalGradient(listOf(Color(0xFF1E1650), PurpleDark)))
                    .padding(20.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Hello,", color = Color.White.copy(alpha = 0.7f))
                        Text("${prefs.merchantName} 👋", color = Color.White, fontSize = 24.sp, fontWeight = FontWeight.Bold)
                    }
                    IconButton(onClick = { nav.navigate("status") }) { Icon(Icons.Filled.Settings, "Status", tint = Color.White) }
                }
                Spacer(Modifier.height(16.dp))
                Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp))
                        .background(Brush.horizontalGradient(listOf(Purple, Color(0xFF7C5CFF)))).padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(Icons.AutoMirrored.Filled.VolumeUp, null, tint = Color.White, modifier = Modifier.size(40.dp))
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text("Sound Box ${if (active) "Active" else "Paused"}", color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                        Text(if (active) "Listening for UPI payments..." else "Turn on to start listening",
                            color = Color.White.copy(alpha = 0.8f), fontSize = 12.sp)
                    }
                    Switch(
                        checked = active,
                        onCheckedChange = { active = it; prefs.soundBoxActive = it },
                        colors = SwitchDefaults.colors(checkedTrackColor = Green, checkedThumbColor = Color.White)
                    )
                }
            }
        }

        // Plan reminder: last 3 days, grace period, or expired
        val days = prefs.daysLeft()
        if (prefs.planUntil > 0 && days < 3) item {
            val msg = when {
                prefs.planActive() && prefs.hasAutopay() ->
                    if (prefs.onTrial) "Free trial ends in ${days + 1} day(s). UPI AutoPay will pay your ${prefs.planLabel().substringBefore(" ·")} plan."
                    else "Your ${prefs.planLabel()} renews by UPI AutoPay in ${days + 1} day(s)."
                prefs.planActive() -> "Your ${prefs.planLabel()} ends in ${days + 1} day(s). Tap to set UPI AutoPay – from ₹1/day."
                prefs.canAnnounce() -> "Plan expired. Voice stops soon. Tap to renew – from ₹1/day."
                else -> "Plan expired – payment voice is OFF. Tap to renew – from ₹1/day."
            }
            Text(
                msg, color = if (prefs.planActive()) PurpleDark else Red, fontWeight = FontWeight.SemiBold, fontSize = 13.sp,
                modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 16.dp).clip(RoundedCornerShape(12.dp))
                    .background(if (prefs.planActive()) PurpleLight else Red.copy(alpha = 0.08f))
                    .clickable { nav.navigate("plans") }.padding(12.dp)
            )
        }
        if (!listenerOn) item {
            Text(
                "⚠ Notification access is off. Tap here to fix it, or no payment will be announced.",
                color = Red, fontWeight = FontWeight.SemiBold, fontSize = 13.sp,
                modifier = Modifier.fillMaxWidth().padding(16.dp).clip(RoundedCornerShape(12.dp))
                    .background(Red.copy(alpha = 0.08f)).clickable { nav.navigate("permissions_again") }.padding(12.dp)
            )
        }
        if (listenerOn && !overlayOn) item {
            Text(
                "Allow \"Display over other apps\" to see the big payment screen when Payvoro is closed. Tap here.",
                color = PurpleDark, fontWeight = FontWeight.SemiBold, fontSize = 13.sp,
                modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 16.dp).clip(RoundedCornerShape(12.dp))
                    .background(PurpleLight).clickable { nav.navigate("permissions_again") }.padding(12.dp)
            )
        }

        item {
            Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                StatCard("Today", rupees(today.sumOf { it.amount }), "${today.size} payments", Modifier.weight(1f))
                StatCard("This Month", rupees(month.sumOf { it.amount }), "${month.size} payments", Modifier.weight(1f))
            }
        }

        item {
            Row(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                QuickAction(Icons.Filled.Receipt, "Transaction History", Modifier.weight(1f)) { nav.goTab("history") }
                QuickAction(Icons.Filled.QrCode2, "Generate QR Code", Modifier.weight(1f)) { nav.goTab("qr") }
                QuickAction(Icons.Filled.Apps, "UPI Apps", Modifier.weight(1f)) { nav.navigate("apps") }
            }
            // Plan upgrade (Test Sound is in Live Status ⚙ and in Profile → Sound Settings)
            Button(
                onClick = { nav.navigate("plans") },
                modifier = Modifier.fillMaxWidth().padding(16.dp).height(50.dp),
                shape = RoundedCornerShape(14.dp)
            ) {
                Icon(Icons.Filled.WorkspacePremium, null)
                Text(
                    when {
                        !prefs.canAnnounce() -> "  Renew Plan"
                        else -> "  My Plan"
                    }
                )
            }
        }

        item {
            Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("Recent Payments", fontWeight = FontWeight.Bold, fontSize = 17.sp, modifier = Modifier.weight(1f))
                TextButton(onClick = { nav.goTab("history") }) { Text("View All") }
            }
        }
        if (all.isEmpty()) item {
            Text("No payments yet. Ask a customer to pay. Test the sound in ⚙ Live Status.", color = TextGray,
                textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(24.dp))
        }
        items(all.take(10), key = { it.id }) { PaymentRow(it) }
    }
}

@Composable
private fun StatCard(title: String, value: String, sub: String, modifier: Modifier) {
    WhiteCard(modifier) {
        Text(title, color = TextGray, fontSize = 12.sp)
        Text(value, fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Text(sub, color = TextGray, fontSize = 11.sp)
    }
}

@Composable
private fun QuickAction(icon: ImageVector, label: String, modifier: Modifier, onClick: () -> Unit) {
    Card(
        modifier.clickable(onClick = onClick), shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White)
    ) {
        Column(Modifier.fillMaxWidth().padding(vertical = 12.dp, horizontal = 4.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(icon, null, tint = Purple)
            Spacer(Modifier.height(4.dp))
            Text(label, fontSize = 10.sp, textAlign = TextAlign.Center, lineHeight = 12.sp)
        }
    }
}
