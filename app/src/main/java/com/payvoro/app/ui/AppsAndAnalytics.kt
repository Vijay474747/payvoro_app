package com.payvoro.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.payvoro.app.data.*
import com.payvoro.app.service.Perms
import java.util.Calendar
import kotlin.math.roundToInt

/** 8. Choose which UPI apps to listen to */
@Composable
fun AppsScreen(onBack: () -> Unit) {
    val ctx = LocalContext.current
    val prefs = remember { Prefs(ctx) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        TopBar("UPI App Selection", onBack)
        WhiteCard(Modifier.fillMaxWidth().padding(16.dp)) {
            UpiApps.all.forEach { app ->
                var on by remember { mutableStateOf(prefs.isAppEnabled(app.id)) }
                val installed = remember { Perms.isInstalled(ctx, app.packages) }
                Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    AppBadge(app.id, 36.dp)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(app.name, fontWeight = FontWeight.SemiBold)
                        Text(if (installed) "Installed" else "Not installed", color = if (installed) Green else TextGray, fontSize = 11.sp)
                    }
                    Switch(checked = on, onCheckedChange = { on = it; prefs.setAppEnabled(app.id, it) },
                        colors = SwitchDefaults.colors(checkedTrackColor = Green))
                }
            }
        }
        Text("UPI app alerts are the main proof – they come in seconds. Bank SMS only adds a second tick (✓✓) " +
            "and never speaks again, even if it comes late.",
            color = TextGray, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 20.dp))

        var refresh by remember { mutableIntStateOf(0) }

        // ---- New payment apps found on this phone ----
        val candApps = remember(refresh) { prefs.candidateApps() }
        val customApps = remember(refresh) { prefs.customApps() }
        if (candApps.isNotEmpty() || customApps.isNotEmpty()) {
            SectionTitle("Other payment apps")
            WhiteCard(Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
                customApps.forEach { (pkg, label) ->
                    TrustRow(label, "Trusted", trusted = true,
                        onTrust = {}, onRemove = { prefs.untrustApp(pkg); refresh++ })
                }
                candApps.forEach { (pkg, label) ->
                    TrustRow(label, "Sent a payment alert. Trust only if this is your payment app.", trusted = false,
                        onTrust = { prefs.trustApp(pkg, label); refresh++ }, onRemove = { prefs.ignoreApp(pkg); refresh++ })
                }
            }
        }

        // ---- Bank SMS ----
        SectionTitle("Bank SMS check")
        WhiteCard(Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
            var last4 by remember { mutableStateOf(prefs.accountLast4) }
            OutlinedTextField(
                value = last4,
                onValueChange = { v -> last4 = v.filter { it.isDigit() }.take(4); prefs.accountLast4 = last4 },
                label = { Text("Bank account – last 4 digits") },
                supportingText = { Text("Only SMS for this account count. Never enter the full number.") },
                singleLine = true,
                keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.NumberPassword),
                modifier = Modifier.fillMaxWidth()
            )
            var speak by remember { mutableStateOf(prefs.announceBankSms) }
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Speak bank-only payments", fontWeight = FontWeight.SemiBold)
                    Text("Turn on only if your QR's app is not on this phone. Bank SMS can be late.", color = TextGray, fontSize = 11.sp)
                }
                Switch(speak, { speak = it; prefs.announceBankSms = it })
            }
            Text("Accepted: bank sender IDs like JD-HDFCBK-T. Ignored: phone numbers, promotional (-P) SMS, " +
                "links, loan / offer / cashback, \"will be credited\", other accounts.",
                color = TextGray, fontSize = 11.sp, modifier = Modifier.padding(top = 8.dp))

            val trusted = remember(refresh) { prefs.trustedSenders() }
            val cand = remember(refresh) { prefs.candidateSenders() }
            trusted.forEach { brand ->
                TrustRow(brand, "Your trusted bank sender", trusted = true, onTrust = {}, onRemove = { prefs.untrustSender(brand); refresh++ })
            }
            if (cand.isNotEmpty()) Text("New bank senders found", fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 12.dp))
            cand.forEach { (brand, sample) ->
                TrustRow(brand, "\"$sample…\"", trusted = false,
                    onTrust = { prefs.trustSender(brand); refresh++ }, onRemove = { prefs.ignoreSender(brand); refresh++ })
            }
        }
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun SectionTitle(text: String) =
    Text(text, fontWeight = FontWeight.Bold, fontSize = 16.sp, modifier = Modifier.padding(start = 20.dp, top = 20.dp, bottom = 8.dp))

@Composable
private fun TrustRow(title: String, sub: String, trusted: Boolean, onTrust: () -> Unit, onRemove: () -> Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.SemiBold)
            Text(sub, color = TextGray, fontSize = 11.sp, maxLines = 2)
        }
        if (trusted) TextButton(onClick = onRemove) { Text("Remove", color = Red) }
        else {
            TextButton(onClick = onRemove) { Text("Ignore") }
            Button(onClick = onTrust) { Text("Trust") }
        }
    }
}

// Analytics screen removed: it was part of the removed Plus plan.
