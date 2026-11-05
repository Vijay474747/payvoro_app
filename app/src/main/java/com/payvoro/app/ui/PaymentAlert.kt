package com.payvoro.app.ui

import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.payvoro.app.data.Payment
import com.payvoro.app.data.SUCCESS
import com.payvoro.app.data.UpiApps
import kotlinx.coroutines.delay
import kotlin.math.abs
import kotlin.math.min
import kotlin.random.Random

/**
 * 4 & 5. Big payment pop-up (green success / red failed), as its own screen so it can show
 * when Payvoro is closed: over other apps and over the lock screen, and it turns the screen on.
 * Opened by [com.payvoro.app.service.PaymentPopup]. Closes itself after a few seconds.
 * A new payment while it is open replaces the old one and restarts the timer.
 */
class PaymentAlertActivity : ComponentActivity() {
    private var payment by mutableStateOf<Payment?>(null)
    private var shownAt by mutableLongStateOf(0L)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        showOverLockScreen()
        val p = fromIntent(intent)
        if (p == null) { finish(); return }
        payment = p
        shownAt = SystemClock.uptimeMillis()
        setContent {
            PayvoroTheme {
                payment?.let { PaymentAlertScreen(it, shownAt) { finish() } }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        fromIntent(intent)?.let { payment = it; shownAt = SystemClock.uptimeMillis() }
    }

    private fun showOverLockScreen() {
        if (Build.VERSION.SDK_INT >= 27) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON)
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    companion object {
        const val AUTO_CLOSE_MS = 7_000L

        fun intent(ctx: Context, p: Payment): Intent = Intent(ctx, PaymentAlertActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_NO_ANIMATION)
            .putExtra("id", p.id)
            .putExtra("amount", p.amount)
            .putExtra("payer", p.payer)
            .putExtra("app", p.app)
            .putExtra("status", p.status)
            .putExtra("time", p.timestamp)

        private fun fromIntent(i: Intent?): Payment? {
            if (i == null || !i.hasExtra("amount")) return null
            return Payment(
                id = i.getLongExtra("id", 0), amount = i.getDoubleExtra("amount", 0.0),
                payer = i.getStringExtra("payer"), app = i.getStringExtra("app") ?: "bank",
                status = i.getStringExtra("status") ?: SUCCESS, rawText = "",
                timestamp = i.getLongExtra("time", System.currentTimeMillis()), dedupeKey = "",
            )
        }
    }
}

/** The pop-up design (matches the reference image). */
@Composable
fun PaymentAlertScreen(p: Payment, key: Long, onClose: () -> Unit) {
    LaunchedEffect(key) { delay(PaymentAlertActivity.AUTO_CLOSE_MS); onClose() }
    val success = p.status == SUCCESS
    val accent = if (success) Color(0xFF22C55E) else Color(0xFFEF4444)
    val deep = if (success) Color(0xFF02170C) else Color(0xFF1C0202)
    val mid = if (success) Color(0xFF075A2D) else Color(0xFF8A1111)

    Box(
        Modifier.fillMaxSize()
            .background(Brush.verticalGradient(listOf(deep, mid, deep)))
            .drawBehind {
                // soft glow behind the title and behind the sound box
                drawRect(Brush.radialGradient(listOf(accent.copy(alpha = 0.30f), Color.Transparent),
                    center = Offset(size.width / 2, size.height * 0.25f), radius = size.width * 0.75f))
                drawRect(Brush.radialGradient(listOf(accent.copy(alpha = 0.40f), Color.Transparent),
                    center = Offset(size.width / 2, size.height * 0.80f), radius = size.width * 0.70f))
            }
    ) {
        if (success) Confetti(Modifier.fillMaxSize())

        Column(
            Modifier.fillMaxSize().systemBarsPadding().padding(horizontal = 24.dp, vertical = 12.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                IconButton(onClick = onClose) { Icon(Icons.Filled.Close, "Close", tint = Color.White) }
            }
            Spacer(Modifier.weight(0.5f))
            Text(
                if (success) "Payment Received!" else "Payment Failed",
                color = Color.White, fontSize = 28.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center
            )
            Spacer(Modifier.height(18.dp))
            Box(
                Modifier.widthIn(min = 200.dp).shadow(16.dp, RoundedCornerShape(20.dp))
                    .clip(RoundedCornerShape(20.dp)).background(Color.White)
                    .padding(horizontal = 32.dp, vertical = 14.dp),
                contentAlignment = Alignment.Center
            ) {
                Text(rupees(p.amount), fontSize = 52.sp, fontWeight = FontWeight.ExtraBold, color = Color(0xFF111827),
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Spacer(Modifier.height(18.dp))
            Box(
                Modifier.size(58.dp).border(3.dp, Color.White.copy(alpha = 0.35f), CircleShape)
                    .padding(4.dp).clip(CircleShape).background(accent),
                contentAlignment = Alignment.Center
            ) {
                Icon(if (success) Icons.Filled.Check else Icons.Filled.Close, null, tint = Color.White, modifier = Modifier.size(32.dp))
            }
            Spacer(Modifier.height(14.dp))
            if (success) {
                if (!p.payer.isNullOrBlank()) {
                    Text("Paid by", color = Color.White.copy(alpha = 0.75f), fontSize = 14.sp)
                    Text(p.payer, color = Color.White, fontSize = 24.sp, fontWeight = FontWeight.Bold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Spacer(Modifier.height(6.dp))
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    AppBadge(p.app, 22.dp)
                    Text("  ${UpiApps.name(p.app)} • ${timeText(p.timestamp)}", color = Color.White.copy(alpha = 0.9f), fontSize = 14.sp)
                }
            } else {
                Text("Payment not received", color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                Text("Please check and try again", color = Color.White.copy(alpha = 0.8f), fontSize = 14.sp)
            }
            Spacer(Modifier.weight(1f))
            SoundBoxGraphic(accent, Modifier.fillMaxWidth().height(210.dp))
            Spacer(Modifier.height(16.dp))
        }
    }
}

/** The sound box device with sound waves on both sides (drawn in code – no image file needed). */
@Composable
fun SoundBoxGraphic(accent: Color, modifier: Modifier = Modifier) {
    val t = rememberInfiniteTransition(label = "waves")
    val phase by t.animateFloat(0f, 1f, infiniteRepeatable(tween(1500, easing = LinearEasing)), label = "phase")

    Canvas(modifier) {
        val w = size.width
        val h = size.height
        val bodyW = min(w * 0.46f, h * 0.95f)
        val bodyH = bodyW * 0.80f
        val cx = w / 2
        val cy = h * 0.50f
        val left = cx - bodyW / 2
        val top = cy - bodyH / 2
        val radius = CornerRadius(bodyW * 0.16f)

        // glow on the "table" under the box
        drawOval(
            Brush.radialGradient(listOf(accent.copy(alpha = 0.65f), Color.Transparent),
                center = Offset(cx, top + bodyH + bodyW * 0.04f), radius = bodyW * 0.75f),
            topLeft = Offset(cx - bodyW * 0.85f, top + bodyH - bodyW * 0.14f),
            size = Size(bodyW * 1.7f, bodyW * 0.36f)
        )
        // top face (gives a 3D look)
        val depth = bodyH * 0.13f
        drawRoundRect(
            Color(0xFF4A505A), topLeft = Offset(left + depth * 0.7f, top - depth),
            size = Size(bodyW - depth * 0.7f, bodyH * 0.35f), cornerRadius = radius
        )
        // body
        drawRoundRect(
            Brush.verticalGradient(listOf(Color(0xFF353A43), Color(0xFF14161A), Color(0xFF0B0C0E)), startY = top, endY = top + bodyH),
            topLeft = Offset(left, top), size = Size(bodyW, bodyH), cornerRadius = radius
        )
        drawRoundRect(
            Color.White.copy(alpha = 0.12f), topLeft = Offset(left, top), size = Size(bodyW, bodyH),
            cornerRadius = radius, style = Stroke(width = 1.5.dp.toPx())
        )
        // speaker
        val sr = bodyH * 0.25f
        val sc = Offset(left + bodyW * 0.36f, cy - bodyH * 0.02f)
        drawCircle(Color(0xFF06080B), radius = sr * 1.28f, center = sc)
        drawCircle(
            Brush.radialGradient(listOf(Color(0xFF60A5FA), Color(0xFF1E3A8A), Color(0xFF0B1220)), center = sc, radius = sr),
            radius = sr, center = sc
        )
        drawCircle(Color(0xFF05070A), radius = sr * 0.38f, center = sc)
        drawCircle(Color.White.copy(alpha = 0.35f), radius = sr * 0.12f, center = Offset(sc.x - sr * 0.45f, sc.y - sr * 0.45f))
        // status light
        drawRoundRect(
            accent, topLeft = Offset(cx - bodyW * 0.07f, top + bodyH * 0.85f),
            size = Size(bodyW * 0.14f, bodyH * 0.04f), cornerRadius = CornerRadius(6f)
        )

        // sound waves: 3 arcs each side, lighting up from the inside out
        val stroke = 5.dp.toPx()
        for (i in 0..2) {
            val d = ((phase * 3f) - i + 3f) % 3f
            val lit = if (d < 1f) 1f - d else 0f
            val alpha = 0.25f + 0.75f * lit
            val r = bodyW * 0.20f + i * bodyW * 0.13f
            for ((center, start) in listOf(Offset(left + bodyW * 0.06f, cy) to 145f, Offset(left + bodyW * 0.94f, cy) to -35f)) {
                val tl = Offset(center.x - r, center.y - r)
                val sz = Size(r * 2, r * 2)
                drawArc(accent.copy(alpha = alpha * 0.35f), start, 70f, false, tl, sz, style = Stroke(stroke * 2.4f, cap = StrokeCap.Round))
                drawArc(accent.copy(alpha = alpha), start, 70f, false, tl, sz, style = Stroke(stroke, cap = StrokeCap.Round))
            }
        }
    }
}

/** Falling confetti for "Payment Received!". */
@Composable
private fun Confetti(modifier: Modifier) {
    val pieces = remember {
        val r = Random(7)
        val colors = listOf(Color(0xFFFACC15), Color(0xFFF472B6), Color(0xFFA78BFA), Color(0xFF60A5FA), Color(0xFFFB923C), Color(0xFF86EFAC))
        List(22) { floatArrayOf(r.nextFloat(), r.nextFloat(), r.nextFloat() * 360f, it % colors.size.toFloat(), 0.6f + r.nextFloat() * 0.6f) } to colors
    }
    val t = rememberInfiniteTransition(label = "confetti")
    val fall by t.animateFloat(0f, 1f, infiniteRepeatable(tween(4000, easing = LinearEasing)), label = "fall")
    Canvas(modifier) {
        val (list, colors) = pieces
        val pw = 5.dp.toPx()
        val ph = 12.dp.toPx()
        list.forEach { f ->
            // left or right side only, so the title and amount stay easy to read
            val x = (if (f[0] < 0.5f) f[0] * 0.56f else 0.44f + f[0] * 0.56f) * size.width
            val y = ((f[1] + fall * f[4] * 0.35f) % 0.5f) * size.height     // stays in the top half
            rotate(f[2] + fall * 360f * f[4], pivot = Offset(x, y)) {
                drawRoundRect(colors[f[3].toInt()], topLeft = Offset(x - pw / 2, y - ph / 2), size = Size(pw, ph),
                    cornerRadius = CornerRadius(2f), alpha = (0.95f - abs(f[1] - 0.25f)).coerceIn(0.4f, 0.95f))
            }
        }
    }
}
