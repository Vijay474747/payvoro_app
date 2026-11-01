package com.payvoro.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.payvoro.app.data.Payment
import com.payvoro.app.data.SUCCESS
import com.payvoro.app.data.UpiApps
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.*

val Purple = Color(0xFF5B3FE8)
val PurpleDark = Color(0xFF3A22B8)
val PurpleLight = Color(0xFFEDE9FF)
val Bg = Color(0xFFF6F5FF)
val Green = Color(0xFF16A34A)
val Red = Color(0xFFDC2626)
val TextGray = Color(0xFF6B7280)
const val DAY = 86_400_000L

@Composable
fun PayvoroTheme(content: @Composable () -> Unit) = MaterialTheme(
    colorScheme = lightColorScheme(primary = Purple, secondary = PurpleDark, background = Bg, surface = Color.White),
    content = content
)

private val inr = NumberFormat.getNumberInstance(Locale("en", "IN")).apply { maximumFractionDigits = 2 }
fun rupees(a: Double): String = "₹" + inr.format(a)
fun timeText(ts: Long): String = SimpleDateFormat("hh:mm a", Locale.ENGLISH).format(Date(ts))

fun startOfDay(ts: Long = System.currentTimeMillis()): Long = Calendar.getInstance().apply {
    timeInMillis = ts
    set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
}.timeInMillis

fun startOfMonth(monthsBack: Int = 0): Long = Calendar.getInstance().apply {
    timeInMillis = startOfDay()
    set(Calendar.DAY_OF_MONTH, 1)
    add(Calendar.MONTH, -monthsBack)
}.timeInMillis

fun dayLabel(ts: Long): String {
    val d = startOfDay(ts)
    val date = SimpleDateFormat("dd MMM yyyy", Locale.ENGLISH).format(Date(ts))
    return when (d) {
        startOfDay() -> "Today, $date"
        startOfDay() - DAY -> "Yesterday, $date"
        else -> date
    }
}

fun minutesAgo(ts: Long): String {
    val m = (System.currentTimeMillis() - ts) / 60_000
    return when {
        m < 1 -> "just now"
        m < 60 -> "$m mins ago"
        m < 1440 -> "${m / 60} hrs ago"
        else -> "${m / 1440} days ago"
    }
}

@Composable
fun PayvoroLogo(size: Dp = 96.dp) {
    Box(
        Modifier.size(size).clip(RoundedCornerShape(size * 0.28f))
            .background(Brush.linearGradient(listOf(Color(0xFF7C5CFF), PurpleDark))),
        contentAlignment = Alignment.Center
    ) {
        Icon(Icons.Filled.PlayArrow, null, tint = Color.White, modifier = Modifier.size(size * 0.6f))
    }
}

@Composable
fun TopBar(title: String, onBack: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        if (onBack != null) IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") }
        else Spacer(Modifier.width(16.dp))
        Text(title, fontSize = 20.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun WhiteCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier,
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(1.dp)
    ) { Column(Modifier.padding(16.dp), content = content) }
}

@Composable
fun PillTabs(options: List<String>, selected: Int, onSelect: (Int) -> Unit) {
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(PurpleLight).padding(4.dp)) {
        options.forEachIndexed { i, s ->
            Box(
                Modifier.weight(1f).clip(RoundedCornerShape(10.dp))
                    .background(if (i == selected) Purple else Color.Transparent)
                    .clickable { onSelect(i) }.padding(vertical = 8.dp),
                contentAlignment = Alignment.Center
            ) {
                Text(s, color = if (i == selected) Color.White else TextGray, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
fun AppBadge(app: String, size: Dp = 40.dp) {
    val (bg, label) = when (app) {
        "gpay" -> Color(0xFF1A73E8) to "G"
        "phonepe" -> Color(0xFF5F259F) to "पे"
        "paytm" -> Color(0xFF00BAF2) to "P"
        "bhim" -> Color(0xFFF57C00) to "B"
        "amazon" -> Color(0xFFFF9900) to "a"
        else -> Color(0xFF0F766E) to "₹"
    }
    Box(Modifier.size(size).clip(CircleShape).background(bg), contentAlignment = Alignment.Center) {
        Text(label, color = Color.White, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun StatusChip(ok: Boolean, text: String = if (ok) "Success" else "Failed") {
    val c = if (ok) Green else Red
    Text(
        text, color = c, fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
        modifier = Modifier.clip(RoundedCornerShape(8.dp)).background(c.copy(alpha = 0.12f))
            .padding(horizontal = 8.dp, vertical = 3.dp)
    )
}

/** Links to the public policy pages on the Payvoro server (Razorpay asks for these). */
@Composable
fun PolicyLinks(modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
        Row { PolicyLink("Terms", "/terms"); PolicyLink("Privacy", "/privacy") }
        Row { PolicyLink("Refund & Cancellation", "/refund"); PolicyLink("Contact", "/contact") }
    }
}

@Composable
private fun PolicyLink(label: String, path: String) {
    val uri = LocalUriHandler.current
    val base = com.payvoro.app.BuildConfig.SERVER_URL.trimEnd('/')
    TextButton(
        onClick = { runCatching { uri.openUri(base + path) } },
        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp)
    ) { Text(label, fontSize = 12.sp) }
}

/**
 * Where this alert came from. Payvoro does NOT verify payments (Razorpay review):
 * it only reads the notification on this phone. Always check your bank app for confirmation.
 */
fun verifyText(p: Payment): String = when (p.source) {
    "app" -> "Alert from ${UpiApps.name(p.app)}"
    else -> "Alert from bank SMS"
}

@Composable
fun VerifyBadge(p: Payment) {
    Text(
        verifyText(p),
        color = PurpleDark,
        fontSize = 11.sp, fontWeight = FontWeight.SemiBold
    )
}

@Composable
fun PaymentRow(p: Payment, showDate: Boolean = true) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        AppBadge(p.app)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(rupees(p.amount), fontWeight = FontWeight.Bold, fontSize = 16.sp)
            Text(p.payer ?: UpiApps.name(p.app), color = TextGray, fontSize = 12.sp)
            if (p.status == SUCCESS) VerifyBadge(p)
        }
        Column(horizontalAlignment = Alignment.End) {
            StatusChip(p.status == SUCCESS)
            Spacer(Modifier.height(4.dp))
            Text(
                if (showDate && startOfDay(p.timestamp) != startOfDay()) dayLabel(p.timestamp).substringBefore(",") + ", " + timeText(p.timestamp)
                else timeText(p.timestamp),
                color = TextGray, fontSize = 11.sp
            )
        }
    }
}
