package com.payvoro.app.ui

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import androidx.compose.foundation.background
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.payvoro.app.data.Prefs
import com.payvoro.app.service.Api
import com.payvoro.app.service.GoogleAuth
import com.payvoro.app.service.UpiQrParser
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Compose's LocalContext can be a wrapper. Credential Manager needs the real Activity. */
private tailrec fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}

/** First page: login with Google. */
@Composable
fun LoginScreen(onLoggedIn: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var showSha1 by remember { mutableStateOf(false) }
    val sha1 = remember { GoogleAuth.appSha1(ctx) }
    val clipboard = LocalClipboardManager.current

    fun login() {
        if (loading) return
        loading = true; error = null; showSha1 = false
        scope.launch {
            val activity = ctx.findActivity()
            val token = when {
                Api.demo -> Result.success("demo")
                activity == null -> Result.failure(Exception("Could not open Google login. Please restart the app."))
                else -> GoogleAuth.idToken(activity)
            }
            val r = token.mapCatching { t -> withContext(Dispatchers.IO) { Api.loginWithGoogle(ctx, t).getOrThrow() } }
            loading = false
            r.onSuccess { onLoggedIn() }.onFailure {
                error = it.message ?: "Login failed"
                showSha1 = (it as? GoogleAuth.LoginError)?.showSha1 == true
            }
        }
    }

    Column(
        Modifier.fillMaxSize()
            .background(Brush.verticalGradient(listOf(Color.White, Color(0xFFE6DFFF))))
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(Modifier.height(40.dp))
        PayvoroLogo(90.dp)
        Text("Payvoro", fontSize = 38.sp, fontWeight = FontWeight.ExtraBold, color = PurpleDark, modifier = Modifier.padding(top = 12.dp))
        Text("Payment Soundbox", color = TextGray)
        if (Api.demo) Text(
            "DEMO MODE – no real Google login or payment",
            color = PurpleDark, fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(top = 12.dp).background(PurpleLight, RoundedCornerShape(8.dp)).padding(horizontal = 10.dp, vertical = 6.dp)
        )
        Spacer(Modifier.height(36.dp))

        WhiteCard(Modifier.fillMaxWidth()) {
            Text("Login", fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Text("Use the Google account on this phone", color = TextGray, fontSize = 13.sp)
            Button(
                onClick = { login() }, enabled = !loading,
                modifier = Modifier.fillMaxWidth().padding(top = 16.dp).height(52.dp),
                shape = RoundedCornerShape(14.dp)
            ) {
                if (loading) CircularProgressIndicator(color = Color.White, strokeWidth = 2.dp, modifier = Modifier.size(22.dp))
                else {
                    Box(Modifier.size(26.dp).clip(CircleShape).background(Color.White), contentAlignment = Alignment.Center) {
                        Text("G", color = Purple, fontWeight = FontWeight.ExtraBold, fontSize = 16.sp)
                    }
                    Text("   Continue with Google", fontSize = 16.sp)
                }
            }
            error?.let { Text(it, color = Red, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp)) }
            if (showSha1) {
                Column(
                    Modifier.fillMaxWidth().padding(top = 10.dp)
                        .background(PurpleLight, RoundedCornerShape(10.dp)).padding(10.dp)
                ) {
                    Text("This app's SHA-1 (add it in Firebase):", fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    SelectionContainer { Text(sha1, fontSize = 12.sp, color = PurpleDark, modifier = Modifier.padding(top = 4.dp)) }
                    TextButton(onClick = { clipboard.setText(AnnotatedString(sha1)) }) { Text("Copy SHA-1") }
                }
            }
        }
        Spacer(Modifier.height(20.dp))
        Text("By continuing you agree to Payvoro's Terms of Service and Privacy Policy.", color = TextGray, fontSize = 11.sp, textAlign = TextAlign.Center)
        PolicyLinks(Modifier.padding(top = 4.dp))
    }
}

/**
 * After the first login: shop name + UPI ID.
 * The scan button opens the QR scanner (it saves the UPI ID and comes back here).
 */
@Composable
fun SetupScreen(onScan: () -> Unit, onDone: () -> Unit) {
    val ctx = LocalContext.current
    val prefs = remember { Prefs(ctx) }
    val scope = rememberCoroutineScope()
    var shop by remember { mutableStateOf(prefs.merchantName.takeIf { it != "My Shop" } ?: "") }
    var upi by remember { mutableStateOf(prefs.upiId) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    // Coming back from the QR scanner: show what it saved
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        if (prefs.upiId.isNotBlank()) upi = prefs.upiId
        if (shop.isBlank() && prefs.merchantName != "My Shop") shop = prefs.merchantName
    }

    fun save() {
        if (shop.trim().length < 2) { error = "Enter your shop name"; return }
        if (!UpiQrParser.isValidVpa(upi.trim())) { error = "Scan your QR, or type your UPI ID (like shop@okaxis)"; return }
        loading = true; error = null
        scope.launch {
            if (upi.trim() != prefs.upiId) prefs.qrRaw = ""
            val r = withContext(Dispatchers.IO) { Api.updateMe(ctx, name = shop.trim(), upiId = upi.trim()) }
            loading = false
            r.onSuccess {
                prefs.merchantName = shop.trim(); prefs.upiId = upi.trim()
                onDone()
            }.onFailure { error = it.message }
        }
    }

    Column(
        Modifier.fillMaxSize()
            .background(Brush.verticalGradient(listOf(Color.White, Color(0xFFE6DFFF))))
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(Modifier.height(32.dp))
        PayvoroLogo(70.dp)
        Spacer(Modifier.height(24.dp))
        WhiteCard(Modifier.fillMaxWidth()) {
            Text("Welcome! 🎉", fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Text("Tell us about your shop. Scan the QR sticker you already use.", color = TextGray, fontSize = 13.sp)
            Spacer(Modifier.height(16.dp))
            OutlinedTextField(
                value = shop, onValueChange = { shop = it.take(60) },
                label = { Text("Shop name") }, singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = upi, onValueChange = { upi = it.trim() },
                label = { Text("UPI ID (e.g. shop@okaxis)") }, singleLine = true,
                trailingIcon = { IconButton(onClick = onScan) { Icon(Icons.Filled.QrCodeScanner, "Scan QR", tint = Purple) } },
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = { save() }),
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp)
            )
            OutlinedButton(onClick = onScan, modifier = Modifier.fillMaxWidth().padding(top = 12.dp)) {
                Icon(Icons.Filled.QrCodeScanner, null); Text("  Scan my shop QR")
            }
            Button(
                onClick = { save() }, enabled = !loading,
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp).height(52.dp),
                shape = RoundedCornerShape(14.dp)
            ) {
                if (loading) CircularProgressIndicator(color = Color.White, strokeWidth = 2.dp, modifier = Modifier.size(22.dp))
                else Text("Continue", fontSize = 16.sp)
            }
            error?.let { Text(it, color = Red, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp)) }
        }
    }
}
