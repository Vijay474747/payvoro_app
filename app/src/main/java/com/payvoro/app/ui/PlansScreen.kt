package com.payvoro.app.ui

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.payvoro.app.data.Prefs
import com.payvoro.app.service.Api
import com.payvoro.app.service.PayRequest
import com.payvoro.app.service.Plan
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Plans: Basic ₹1.8/day and Plus ₹3.5/day, paid monthly by UPI AutoPay (₹54 / ₹105).
 * firstTime = right after setup. There is no back button; Home opens once AutoPay is set.
 */
@Composable
fun PlansScreen(firstTime: Boolean, onBack: (() -> Unit)?, onActivated: () -> Unit) {
    val ctx = LocalContext.current
    val prefs = remember { Prefs(ctx) }
    val scope = rememberCoroutineScope()
    var plans by remember { mutableStateOf(Api.defaultPlans) }
    var busy by remember { mutableStateOf<String?>(null) }
    var waiting by remember { mutableStateOf<String?>(null) }
    var linkReq by remember { mutableStateOf<PayRequest?>(null) }
    var checking by remember { mutableStateOf(false) }

    // Coming back from the Razorpay page → ask the server for the new plan
    var tick by remember { mutableIntStateOf(0) }
    var refreshed by remember { mutableIntStateOf(0) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { tick++ }
    LaunchedEffect(tick) { withContext(Dispatchers.IO) { Api.refreshMe(ctx) }; refreshed++ }
    LaunchedEffect(Unit) { withContext(Dispatchers.IO) { Api.plans() }.onSuccess { plans = it } }
    // While waiting for Razorpay's confirmation, check again every 5 seconds (2 minutes max)
    LaunchedEffect(checking) {
        if (!checking) return@LaunchedEffect
        repeat(24) {
            delay(5000)
            withContext(Dispatchers.IO) { Api.refreshMe(ctx) }
            refreshed++
            if (!prefs.needsPlan && firstTime) return@LaunchedEffect
        }
        checking = false
    }
    // First time: as soon as AutoPay is confirmed, go on
    LaunchedEffect(refreshed) { if (firstTime && !prefs.needsPlan) onActivated() }

    // re-read after each refresh
    val plan = remember(refreshed) { prefs.plan }
    val until = remember(refreshed) { prefs.planUntil }
    val autopay = remember(refreshed) { prefs.hasAutopay() }
    val active = until > System.currentTimeMillis()
    val dateText = SimpleDateFormat("dd MMM yyyy", Locale.ENGLISH).format(Date(until))

    fun open(url: String) = try {
        ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        true
    } catch (e: ActivityNotFoundException) {
        Toast.makeText(ctx, "No browser found on this phone", Toast.LENGTH_LONG).show(); false
    }

    fun handle(p: Plan, r: Result<PayRequest>) = r.onSuccess { req ->
        when (req.method) {
            "demo" -> {
                refreshed++
                waiting = if (req.trial) "Demo mode: ${p.name} is ON. $TRIAL free days started. No money was taken."
                          else "Demo mode: ${p.name} plan is ON for 30 days. No money was taken."
                if (!firstTime) onActivated()
            }
            "link" -> linkReq = req                       // ask to use the same email first
            "manual" -> if (open(req.url)) waiting =
                "Pay ₹${req.amount} on the page that opened. Your plan turns on after we check the payment " +
                "(usually within a few hours). Request #${req.requestId}."
            else -> if (open(req.url)) {                  // autopay
                waiting = "Approve UPI AutoPay on the Razorpay page, then come back here."
                checking = true
            }
        }
    }.onFailure { Toast.makeText(ctx, it.message, Toast.LENGTH_LONG).show() }

    fun startAutopay(p: Plan) {
        busy = p.id
        scope.launch {
            val r = withContext(Dispatchers.IO) { Api.subscribe(ctx, p.id) }
            busy = null
            handle(p, r)
        }
    }

    fun payByLink(p: Plan) {
        busy = p.id
        scope.launch {
            val r = withContext(Dispatchers.IO) { Api.payManually(ctx, p.id) }
            busy = null
            handle(p, r)
        }
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        TopBar(if (firstTime) "Choose your plan" else "Plans", onBack)
        Column(Modifier.padding(horizontal = 16.dp)) {
            if (firstTime) {
                // Free trial banner
                Column(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp))
                        .background(Brush.horizontalGradient(listOf(PurpleDark, Purple))).padding(18.dp)
                ) {
                    Text("🎉  First $TRIAL days FREE", color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                    Text("Set UPI AutoPay now. No money is taken for $TRIAL days. Stop any time from your UPI app.",
                        color = Color.White.copy(alpha = 0.9f), fontSize = 13.sp)
                }
            } else {
                // Current plan
                Column(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp))
                        .background(Brush.horizontalGradient(if (active) listOf(PurpleDark, Purple) else listOf(Color(0xFF7F1D1D), Red)))
                        .padding(18.dp)
                ) {
                    Text("Your plan", color = Color.White.copy(alpha = 0.8f))
                    Text(prefs.planLabel(), color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Bold)
                    Text(
                        when {
                            until == 0L -> "Not active"
                            active && prefs.onTrial -> "Free till $dateText (${prefs.daysLeft()} days left). AutoPay starts after that."
                            active -> "Valid till $dateText (${prefs.daysLeft()} days left)"
                            prefs.canAnnounce() -> "Expired on $dateText – voice stops in 3 days. Please renew."
                            else -> "Expired on $dateText – voice is off. Renew to turn it on."
                        },
                        color = Color.White, fontSize = 13.sp
                    )
                    Text(
                        when (prefs.autopayStatus) {
                            "authenticated", "active" -> "UPI AutoPay: ON"
                            "pending", "halted" -> "UPI AutoPay: last payment failed. Check your UPI app balance."
                            "cancelled" -> "UPI AutoPay: stopped"
                            else -> "UPI AutoPay: not set"
                        },
                        color = Color.White.copy(alpha = 0.85f), fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp)
                    )
                }
            }
            waiting?.let {
                Row(
                    Modifier.fillMaxWidth().padding(top = 12.dp).clip(RoundedCornerShape(12.dp)).background(PurpleLight).padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    if (checking) CircularProgressIndicator(strokeWidth = 2.dp, modifier = Modifier.size(18.dp).padding(end = 0.dp))
                    Text((if (checking) "  " else "") + it, color = PurpleDark, fontSize = 13.sp)
                }
            }
            Spacer(Modifier.height(8.dp))
            plans.forEach { p ->
                val current = active && plan == p.id && autopay
                val best = p.id == "plus"
                Card(
                    Modifier.fillMaxWidth().padding(vertical = 8.dp),
                    shape = RoundedCornerShape(18.dp),
                    colors = CardDefaults.cardColors(containerColor = Color.White),
                    border = if (best) BorderStroke(2.dp, Purple) else null
                ) {
                    Column(Modifier.padding(18.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(p.name, fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                            if (best) StatusChip(true, "Most popular")
                        }
                        Row(verticalAlignment = Alignment.Bottom) {
                            Text("₹${p.perDay}", fontSize = 34.sp, fontWeight = FontWeight.ExtraBold, color = PurpleDark)
                            Text(" / day", color = TextGray, modifier = Modifier.padding(bottom = 6.dp))
                        }
                        Text("Paid monthly by UPI AutoPay (₹${p.price}/month)", color = TextGray, fontSize = 12.sp)
                        Spacer(Modifier.height(6.dp))
                        p.features.forEach { f ->
                            Row(Modifier.padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Filled.Check, null, tint = Green, modifier = Modifier.size(18.dp))
                                Text("  $f", fontSize = 14.sp)
                            }
                        }
                        Button(
                            onClick = { startAutopay(p) }, enabled = busy == null && !current,
                            modifier = Modifier.fillMaxWidth().padding(top = 12.dp).height(48.dp),
                            colors = if (best) ButtonDefaults.buttonColors() else ButtonDefaults.buttonColors(containerColor = PurpleDark)
                        ) {
                            if (busy == p.id) CircularProgressIndicator(color = Color.White, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
                            else Text(
                                when {
                                    current -> "AutoPay is ON ✓"
                                    firstTime || prefs.planUntil == 0L -> "Start $TRIAL days free"
                                    active && plan == "basic" && p.id == "plus" -> "Upgrade to Plus"
                                    active && plan != p.id -> "Switch to ${p.name}"
                                    else -> "Set UPI AutoPay"
                                }
                            )
                        }
                        if (!current) TextButton(
                            onClick = { payByLink(p) }, enabled = busy == null,
                            modifier = Modifier.align(Alignment.CenterHorizontally)
                        ) { Text("Can't use AutoPay? Pay 1 month by link", fontSize = 12.sp) }
                    }
                }
            }
            Text(
                "UPI AutoPay is by Razorpay. The first $TRIAL days are free (first plan only). " +
                    "When you switch plan, the old AutoPay is stopped. Stop AutoPay any time from your UPI app.",
                color = TextGray, fontSize = 12.sp, modifier = Modifier.padding(vertical = 12.dp)
            )
        }
    }

    // Your ready-made AutoPay link: the email must match the Google login so we can find the merchant
    linkReq?.let { req ->
        AlertDialog(
            onDismissRequest = { linkReq = null },
            title = { Text("Set UPI AutoPay") },
            text = {
                Column {
                    Text("On the Razorpay page, enter this same email:", fontSize = 14.sp)
                    Text(req.email.ifBlank { prefs.email }, fontWeight = FontWeight.Bold, fontSize = 16.sp, color = PurpleDark,
                        modifier = Modifier.padding(vertical = 8.dp))
                    Text("Then approve AutoPay of ₹${req.amount}/month in your UPI app" +
                        (if (req.trial) " (first $TRIAL days free)." else "."), fontSize = 14.sp)
                    Text("Your plan turns on by itself in a few seconds.", color = TextGray, fontSize = 12.sp,
                        textAlign = TextAlign.Start, modifier = Modifier.padding(top = 8.dp))
                }
            },
            confirmButton = {
                Button(onClick = {
                    if (open(req.url)) { waiting = "Approve UPI AutoPay on the Razorpay page, then come back here."; checking = true }
                    linkReq = null
                }) { Text("Open Razorpay") }
            },
            dismissButton = { TextButton(onClick = { linkReq = null }) { Text("Cancel") } }
        )
    }
}

private const val TRIAL = Api.TRIAL_DAYS
