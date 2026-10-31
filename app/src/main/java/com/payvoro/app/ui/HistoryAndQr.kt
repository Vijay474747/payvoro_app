package com.payvoro.app.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color as AColor
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import android.widget.Toast
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material.icons.filled.Share
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.payvoro.app.service.Api
import com.payvoro.app.service.UpiQrParser
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.qrcode.QRCodeWriter
import com.google.zxing.qrcode.decoder.ErrorCorrectionLevel
import com.payvoro.app.data.AppDatabase
import com.payvoro.app.data.FAILED
import com.payvoro.app.data.Prefs
import com.payvoro.app.data.SUCCESS
import java.io.File
import java.util.Locale

/** 6. Transaction history, grouped by day */
@Composable
fun HistoryScreen(onUpgrade: () -> Unit) {
    val ctx = LocalContext.current
    val prefs = remember { Prefs(ctx) }
    val all by remember { AppDatabase.get(ctx).payments().all() }.collectAsState(initial = emptyList())
    var tab by remember { mutableIntStateOf(0) }
    // Basic plan shows the last 30 days; Plus/trial shows everything
    val cutoff = if (prefs.isPlus()) 0L else startOfDay() - 29 * DAY
    val visible = all.filter { it.timestamp >= cutoff }
    val hidden = all.size - visible.size
    val list = when (tab) {
        1 -> visible.filter { it.status == SUCCESS }
        2 -> visible.filter { it.status == FAILED }
        else -> visible
    }
    val groups = list.groupBy { dayLabel(it.timestamp) }

    Column(Modifier.fillMaxSize()) {
        TopBar("Transaction History")
        Box(Modifier.padding(horizontal = 16.dp)) { PillTabs(listOf("All", "Success", "Failed"), tab) { tab = it } }
        LazyColumn(Modifier.fillMaxSize()) {
            if (list.isEmpty()) item {
                Text("No transactions", color = TextGray, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(32.dp))
            }
            groups.forEach { (day, dayItems) ->
                item(key = day) {
                    Text(day, color = TextGray, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(start = 16.dp, top = 16.dp, bottom = 4.dp))
                }
                items(dayItems, key = { it.id }) { PaymentRow(it, showDate = false) }
            }
            if (hidden > 0) item {
                TextButton(onClick = onUpgrade, modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                    Text("$hidden older payments are saved. Upgrade to Plus to see them.")
                }
            }
        }
    }
}

/** 7. QR code generator – standard UPI QR, money goes straight to the merchant's own bank */
@Composable
fun QrScreen(onScan: () -> Unit) {
    val ctx = LocalContext.current
    val prefs = remember { Prefs(ctx) }
    val scope = rememberCoroutineScope()
    var mode by remember { mutableIntStateOf(0) }
    var amountText by remember { mutableStateOf("") }
    var tick by remember { mutableIntStateOf(0) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { tick++ }      // re-read after scanning
    val upi = remember(tick) { prefs.upiId }
    val scanned = remember(tick) { prefs.qrRaw.takeIf { it.isNotBlank() }?.let { UpiQrParser.parse(it) } }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.weight(1f)) { TopBar("My QR Code") }
            if (upi.isNotBlank()) TextButton(onClick = onScan) {
                Icon(Icons.Filled.QrCodeScanner, null); Text(" Scan new")
            }
        }
        if (upi.isBlank()) {
            // First time: scan the shop's existing QR, or type the UPI ID
            var manual by remember { mutableStateOf("") }
            var err by remember { mutableStateOf<String?>(null) }
            WhiteCard(Modifier.fillMaxWidth().padding(16.dp)) {
                Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Filled.QrCodeScanner, null, tint = Purple, modifier = Modifier.size(72.dp))
                    Text("Already have a shop QR?", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    Text("Scan it once. We read your UPI ID from it.", color = TextGray, textAlign = TextAlign.Center)
                    Button(onClick = onScan, modifier = Modifier.fillMaxWidth().padding(top = 16.dp).height(52.dp)) {
                        Icon(Icons.Filled.CameraAlt, null); Text("  Scan my QR")
                    }
                }
            }
            Text("Or type your UPI ID", fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(horizontal = 20.dp))
            Row(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(manual, { manual = it.trim(); err = null }, placeholder = { Text("shopname@okaxis") },
                    singleLine = true, isError = err != null, modifier = Modifier.weight(1f))
                Button(onClick = {
                    if (!UpiQrParser.isValidVpa(manual)) { err = "This UPI ID looks wrong"; return@Button }
                    prefs.upiId = manual; prefs.qrRaw = ""; tick++
                    scope.launch { withContext(Dispatchers.IO) { Api.updateMe(ctx, upiId = manual) } }
                }, modifier = Modifier.padding(start = 8.dp)) { Text("Save") }
            }
            err?.let { Text(it, color = Red, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 20.dp)) }
            return@Column
        }
        Column(Modifier.padding(horizontal = 16.dp)) {
            PillTabs(listOf("Static QR", "Amount QR"), mode) { mode = it }
            if (mode == 1) OutlinedTextField(
                value = amountText, onValueChange = { v -> amountText = v.filter { it.isDigit() || it == '.' } },
                label = { Text("Amount (₹)") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp)
            )
            val amount = if (mode == 1) amountText.toDoubleOrNull() else null
            val link = remember(upi, amount, scanned) { UpiQrParser.withAmount(scanned, upi, prefs.merchantName, amount) }
            val bmp = remember(link) { UpiQr.bitmap(link, 720) }

            WhiteCard(Modifier.fillMaxWidth().padding(vertical = 16.dp)) {
                Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
                    Image(bmp.asImageBitmap(), "UPI QR", modifier = Modifier.size(250.dp))
                    Text(if (amount != null) "Pay ${rupees(amount)}" else "Scan and Pay", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    Text(prefs.merchantName, color = TextGray)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("UPI ID: $upi", fontWeight = FontWeight.SemiBold)
                        IconButton(onClick = {
                            ctx.getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("UPI ID", upi))
                            Toast.makeText(ctx, "UPI ID copied", Toast.LENGTH_SHORT).show()
                        }) { Icon(Icons.Filled.ContentCopy, "Copy", tint = Purple) }
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedButton(onClick = { UpiQr.share(ctx, bmp) }, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Filled.Share, null); Text("  Share QR")
                }
                Button(onClick = {
                    val ok = UpiQr.saveToGallery(ctx, bmp)
                    Toast.makeText(ctx, if (ok) "Saved to Pictures/Payvoro" else "Use Share to save on this phone", Toast.LENGTH_SHORT).show()
                }, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Filled.Download, null); Text("  Download")
                }
            }
            Text((if (scanned != null) "This is your own shop QR (scanned). " else "") +
                "Money goes straight to your own bank account. Payvoro never holds your money.",
                color = TextGray, fontSize = 12.sp, modifier = Modifier.padding(vertical = 16.dp))
        }
    }
}

object UpiQr {
    fun link(vpa: String, name: String, amount: Double?): String {
        val b = StringBuilder("upi://pay?pa=").append(Uri.encode(vpa))
            .append("&pn=").append(Uri.encode(name)).append("&cu=INR")
        if (amount != null && amount > 0) b.append("&am=").append(String.format(Locale.US, "%.2f", amount))
        return b.toString()
    }

    fun bitmap(text: String, size: Int): Bitmap {
        val hints = mapOf(EncodeHintType.MARGIN to 1, EncodeHintType.ERROR_CORRECTION to ErrorCorrectionLevel.M)
        val m = QRCodeWriter().encode(text, BarcodeFormat.QR_CODE, size, size, hints)
        val px = IntArray(size * size) { i -> if (m[i % size, i / size]) AColor.BLACK else AColor.WHITE }
        return Bitmap.createBitmap(px, size, size, Bitmap.Config.ARGB_8888)
    }

    fun saveToGallery(ctx: Context, bmp: Bitmap): Boolean {
        if (Build.VERSION.SDK_INT < 29) return false
        return runCatching {
            val values = ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, "payvoro_qr_${System.currentTimeMillis()}.png")
                put(MediaStore.Images.Media.MIME_TYPE, "image/png")
                put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/Payvoro")
            }
            val uri = ctx.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: return false
            ctx.contentResolver.openOutputStream(uri)?.use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
            true
        }.getOrDefault(false)
    }

    fun share(ctx: Context, bmp: Bitmap) {
        val dir = File(ctx.cacheDir, "qr").apply { mkdirs() }
        val file = File(dir, "payvoro_qr.png")
        file.outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
        val uri = FileProvider.getUriForFile(ctx, ctx.packageName + ".files", file)
        val send = Intent(Intent.ACTION_SEND).setType("image/png")
            .putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        ctx.startActivity(Intent.createChooser(send, "Share QR"))
    }
}
