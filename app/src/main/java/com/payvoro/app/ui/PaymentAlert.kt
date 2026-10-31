package com.payvoro.app.ui

import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Speaker
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.payvoro.app.data.Payment
import com.payvoro.app.data.SUCCESS
import com.payvoro.app.data.UpiApps
import kotlinx.coroutines.delay

/** 4 & 5. Full-screen payment alert (green success / red failed). Closes itself after 6 seconds. */
@Composable
fun PaymentAlertDialog(p: Payment, onClose: () -> Unit) {
    LaunchedEffect(p.id) { delay(6000); onClose() }
    val success = p.status == SUCCESS
    val colors = if (success) listOf(Color(0xFF03301A), Color(0xFF0B8A43)) else listOf(Color(0xFF3D0707), Color(0xFFB91C1C))
    val pulse = rememberInfiniteTransition(label = "pulse")
    val scale by pulse.animateFloat(1f, 1.12f, infiniteRepeatable(tween(600), RepeatMode.Reverse), label = "scale")

    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(colors)).padding(24.dp)) {
            IconButton(onClick = onClose, modifier = Modifier.align(Alignment.TopEnd)) {
                Icon(Icons.Filled.Close, "Close", tint = Color.White)
            }
            Column(Modifier.align(Alignment.Center), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(if (success) "Payment Received!" else "Payment Failed", color = Color.White, fontSize = 30.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(20.dp))
                Box(Modifier.clip(RoundedCornerShape(22.dp)).background(Color.White).padding(horizontal = 36.dp, vertical = 18.dp)) {
                    Text(rupees(p.amount), fontSize = 52.sp, fontWeight = FontWeight.ExtraBold, color = Color(0xFF111827))
                }
                Spacer(Modifier.height(16.dp))
                Box(Modifier.size(56.dp).clip(CircleShape).background(if (success) Green else Red), contentAlignment = Alignment.Center) {
                    Icon(if (success) Icons.Filled.Check else Icons.Filled.Close, null, tint = Color.White, modifier = Modifier.size(34.dp))
                }
                Spacer(Modifier.height(16.dp))
                if (success) {
                    Text("Paid by", color = Color.White.copy(alpha = 0.75f))
                    Text(p.payer ?: "Customer", color = Color.White, fontSize = 24.sp, fontWeight = FontWeight.Bold)
                    Text("${UpiApps.name(p.app)} • ${timeText(p.timestamp)}", color = Color.White.copy(alpha = 0.85f))
                    Text(verifyText(p), color = Color.White, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 6.dp))
                } else {
                    Text("Payment not received", color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                    Text("Please check and try again", color = Color.White.copy(alpha = 0.8f))
                }
                Spacer(Modifier.height(40.dp))
                Icon(Icons.Filled.Speaker, null, tint = if (success) Color(0xFF4ADE80) else Color(0xFFFCA5A5),
                    modifier = Modifier.size(140.dp).scale(scale))
            }
        }
    }
}
