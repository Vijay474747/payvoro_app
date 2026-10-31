package com.payvoro.app.ui

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.google.zxing.*
import com.google.zxing.common.HybridBinarizer
import com.payvoro.app.data.Prefs
import com.payvoro.app.service.Api
import com.payvoro.app.service.ScannedUpi
import com.payvoro.app.service.UpiQrParser
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.concurrent.Executors

/** Scan the shop's existing QR sticker (camera or gallery photo) and save its UPI ID. */
@Composable
fun QrScanScreen(onDone: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var hasCam by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(ctx, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    val camLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { hasCam = it }
    LaunchedEffect(Unit) { if (!hasCam) camLauncher.launch(Manifest.permission.CAMERA) }

    var found by remember { mutableStateOf<ScannedUpi?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }

    val onText: (String) -> Unit = { text ->
        if (found == null) {
            val p = UpiQrParser.parse(text)
            if (p != null) { found = p; error = null } else error = "This is not a UPI payment QR. Try your shop's payment QR."
        }
    }
    val gallery = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) scope.launch {
            val text = withContext(Dispatchers.Default) { QrDecode.fromImage(ctx, uri) }
            if (text == null) error = "No QR found in this photo. Try a clearer photo." else onText(text)
        }
    }

    Column(Modifier.fillMaxSize()) {
        TopBar("Scan your shop QR", onDone)
        Box(Modifier.weight(1f).fillMaxWidth().background(Color.Black), contentAlignment = Alignment.Center) {
            if (hasCam && found == null) CameraQrView(onText)
            else if (!hasCam) Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(24.dp)) {
                Text("Camera permission is needed to scan.", color = Color.White, textAlign = TextAlign.Center)
                Button(onClick = { camLauncher.launch(Manifest.permission.CAMERA) }, modifier = Modifier.padding(top = 12.dp)) { Text("Allow Camera") }
            }
            // Scan frame
            Box(Modifier.size(240.dp).border(3.dp, Color.White, RoundedCornerShape(20.dp)))
        }
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Text("Point the camera at the QR sticker you already use (from your bank, GPay, PhonePe or Paytm).",
                color = TextGray, fontSize = 13.sp)
            error?.let { Text(it, color = Red, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp)) }
            OutlinedButton(onClick = { gallery.launch("image/*") }, modifier = Modifier.fillMaxWidth().padding(top = 12.dp)) {
                Icon(Icons.Filled.PhotoLibrary, null); Text("  Pick QR photo from Gallery")
            }
        }
    }

    found?.let { s ->
        var name by remember(s) { mutableStateOf(s.name ?: Prefs(ctx).merchantName) }
        AlertDialog(
            onDismissRequest = { found = null },
            title = { Text("QR found ✓") },
            text = {
                Column {
                    Text("UPI ID", color = TextGray, fontSize = 12.sp)
                    Text(s.vpa, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                    Spacer(Modifier.height(12.dp))
                    OutlinedTextField(name, { name = it }, label = { Text("Shop name") }, singleLine = true)
                    Text("Customers' money still goes straight to this account.", color = TextGray, fontSize = 12.sp,
                        modifier = Modifier.padding(top = 8.dp))
                }
            },
            confirmButton = {
                Button(enabled = !saving, onClick = {
                    saving = true
                    scope.launch {
                        val prefs = Prefs(ctx)
                        prefs.upiId = s.vpa
                        prefs.qrRaw = s.raw
                        if (name.isNotBlank()) prefs.merchantName = name.trim()
                        val r = withContext(Dispatchers.IO) { Api.updateMe(ctx, name.trim().takeIf { it.length >= 2 }, s.vpa) }
                        saving = false
                        Toast.makeText(ctx, if (r.isSuccess) "UPI ID saved" else "Saved on phone. Will sync later.", Toast.LENGTH_SHORT).show()
                        onDone()
                    }
                }) { Text("Save") }
            },
            dismissButton = { TextButton(onClick = { found = null }) { Text("Scan again") } }
        )
    }
}

@Composable
private fun CameraQrView(onText: (String) -> Unit) {
    val ctx = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val mainExec = remember { ContextCompat.getMainExecutor(ctx) }
    val analysisExec = remember { Executors.newSingleThreadExecutor() }
    DisposableEffect(Unit) { onDispose { analysisExec.shutdown() } }

    AndroidView(
        modifier = Modifier.fillMaxSize(),
        factory = { c ->
            val view = PreviewView(c)
            val future = ProcessCameraProvider.getInstance(c)
            future.addListener({
                val provider = future.get()
                val preview = Preview.Builder().build().also { it.setSurfaceProvider(view.surfaceProvider) }
                val analysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build()
                analysis.setAnalyzer(analysisExec, QrAnalyzer { text -> mainExec.execute { onText(text) } })
                runCatching {
                    provider.unbindAll()
                    provider.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
                }.onFailure { Toast.makeText(c, "Camera could not start. Use Gallery instead.", Toast.LENGTH_LONG).show() }
            }, mainExec)
            view
        }
    )
}

/** Reads QR codes from camera frames using ZXing (works offline, no Google Play Services needed). */
private class QrAnalyzer(private val onText: (String) -> Unit) : ImageAnalysis.Analyzer {
    private val reader = MultiFormatReader().apply {
        setHints(mapOf(DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE), DecodeHintType.TRY_HARDER to true))
    }
    private var last = 0L

    override fun analyze(image: ImageProxy) {
        try {
            val now = System.currentTimeMillis()
            if (now - last < 250) return
            last = now
            val plane = image.planes[0]          // Y (brightness) plane is enough for QR
            val buf = plane.buffer
            val data = ByteArray(buf.remaining()).also { buf.get(it) }
            val src = PlanarYUVLuminanceSource(data, plane.rowStride, image.height, 0, 0, image.width, image.height, false)
            val result = runCatching { reader.decodeWithState(BinaryBitmap(HybridBinarizer(src))) }.getOrNull()
                ?: runCatching { reader.decodeWithState(BinaryBitmap(HybridBinarizer(src.invert()))) }.getOrNull()
            result?.text?.let(onText)
        } finally {
            reader.reset()
            image.close()
        }
    }
}

object QrDecode {
    fun fromImage(ctx: Context, uri: Uri): String? = runCatching { decode(ctx, uri) }.getOrNull()

    private fun decode(ctx: Context, uri: Uri): String? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        ctx.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
        var sample = 1
        while (maxOf(bounds.outWidth, bounds.outHeight) / sample > 1600) sample *= 2
        val bmp = ctx.contentResolver.openInputStream(uri)?.use {
            BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample })
        } ?: return null
        val px = IntArray(bmp.width * bmp.height)
        bmp.getPixels(px, 0, bmp.width, 0, 0, bmp.width, bmp.height)
        val src = RGBLuminanceSource(bmp.width, bmp.height, px)
        val hints = mapOf(DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE), DecodeHintType.TRY_HARDER to true)
        val reader = MultiFormatReader().apply { setHints(hints) }
        return runCatching { reader.decodeWithState(BinaryBitmap(HybridBinarizer(src))).text }.getOrNull()
            ?: runCatching { reader.decodeWithState(BinaryBitmap(HybridBinarizer(src.invert()))).text }.getOrNull()
    }
}
