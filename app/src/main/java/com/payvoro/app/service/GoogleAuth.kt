package com.payvoro.app.service

import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log
import androidx.credentials.Credential
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import androidx.credentials.exceptions.NoCredentialException
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.payvoro.app.BuildConfig
import java.security.MessageDigest

/**
 * Shows Google's account picker and returns an ID token. The server checks it.
 *
 * Most "Login cancelled" / "No credentials" errors are NOT the user. They are Google
 * refusing the app because the setup in Firebase / Google Cloud does not match this APK:
 *   - wrong / placeholder Web client ID
 *   - the APK's SHA-1 is not added to an "Android" OAuth client (error [16])
 *   - OAuth consent screen is in "Testing" and this Gmail is not a test user
 * So this file now tells the user (and you) which one it is.
 */
object GoogleAuth {
    private const val TAG = "PayvoroGoogle"

    /** Thrown with a clear message. [showSha1] = true means "show the SHA-1 box on screen". */
    class LoginError(message: String, val showSha1: Boolean = false) : Exception(message)

    private fun looksWrong(id: String) =
        id.isBlank() || id.startsWith("YOUR_") || !id.endsWith(".apps.googleusercontent.com")

    /**
     * The Web client ID.
     * 1st choice: from Firebase's google-services.json (the plugin makes R.string.default_web_client_id).
     * 2nd choice: GOOGLE_WEB_CLIENT_ID in app/build.gradle.kts.
     */
    fun webClientId(ctx: Context): String {
        val resId = ctx.resources.getIdentifier("default_web_client_id", "string", ctx.packageName)
        if (resId != 0) {
            val fromFirebase = ctx.getString(resId)
            if (!looksWrong(fromFirebase)) return fromFirebase
        }
        return BuildConfig.GOOGLE_WEB_CLIENT_ID
    }

    suspend fun idToken(activity: Activity): Result<String> {
        val clientId = webClientId(activity)
        if (looksWrong(clientId)) return Result.failure(LoginError(
            "App setup: no Web client ID. Put Firebase's google-services.json in the app/ folder " +
                "(or set GOOGLE_WEB_CLIENT_ID in app/build.gradle.kts) and build again."))
        Log.i(TAG, "Using Web client ID: $clientId, package: ${activity.packageName}, SHA-1: ${appSha1(activity)}")

        val cm = CredentialManager.create(activity)

        // 1st try: the "Sign in with Google" button flow.
        val first = runCatching {
            val option = GetSignInWithGoogleOption.Builder(clientId).build()
            cm.getCredential(activity, GetCredentialRequest.Builder().addCredentialOption(option).build()).credential
        }
        first.getOrNull()?.let { return tokenFrom(it) }
        val e1 = first.exceptionOrNull()
        Log.w(TAG, "SignInWithGoogle failed: ${e1?.javaClass?.simpleName}: ${e1?.message}", e1)

        // A real "user pressed back" → stop here, don't open a 2nd sheet.
        if (e1 is GetCredentialCancellationException && !isSetupProblem(e1)) {
            return Result.failure(LoginError("Login cancelled"))
        }

        // 2nd try: the bottom-sheet flow, showing all accounts on the phone.
        val second = runCatching {
            val option = GetGoogleIdOption.Builder()
                .setServerClientId(clientId)
                .setFilterByAuthorizedAccounts(false)
                .setAutoSelectEnabled(false)
                .build()
            cm.getCredential(activity, GetCredentialRequest.Builder().addCredentialOption(option).build()).credential
        }
        second.getOrNull()?.let { return tokenFrom(it) }
        val e2 = second.exceptionOrNull() ?: e1
        Log.w(TAG, "GoogleIdOption failed: ${e2?.javaClass?.simpleName}: ${e2?.message}", e2)

        return Result.failure(explain(e2 ?: e1))
    }

    private fun tokenFrom(cred: Credential): Result<String> =
        if (cred is CustomCredential && cred.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL)
            Result.success(GoogleIdTokenCredential.createFrom(cred.data).idToken)
        else Result.failure(LoginError("Please choose a Google account"))

    /** Error [16] "Account reauth failed" = Google rejected this APK (SHA-1 / client ID mismatch). */
    private fun isSetupProblem(e: Throwable?): Boolean {
        val m = e?.message.orEmpty().lowercase()
        return "[16]" in m || "reauth" in m || "developer" in m || "[10]" in m
    }

    private fun explain(e: Throwable?): LoginError {
        val raw = e?.message?.takeIf { it.isNotBlank() } ?: e?.javaClass?.simpleName ?: "unknown"
        return when {
            isSetupProblem(e) -> LoginError(
                "Google blocked this app ($raw).\n" +
                    "Fix: Firebase → Project settings → Android app com.payvoro.app → add the SHA-1 " +
                    "shown below. Also add your Gmail as a test user if the consent screen is in Testing.",
                    showSha1 = true)
            // NoCredentialException does NOT mean "no account on the phone" most of the time.
            // Google also throws it when this APK's package + SHA-1 is not registered
            // (Firebase → Project settings → Your Android app → SHA fingerprints).
            // So we show the SHA-1 box here too.
            e is NoCredentialException -> LoginError(
                "Google did not allow login ($raw).\n" +
                    "Most common reason: this app's SHA-1 (below) is not added in Firebase → " +
                    "Project settings → Android app com.payvoro.app. Add it, wait 5 minutes, try again.\n" +
                    "Also check the phone has a Google account (Settings → Accounts).", showSha1 = true)
            e is GetCredentialCancellationException -> LoginError(
                "Login cancelled ($raw). If you did not cancel, the app's SHA-1 below is probably " +
                    "missing in Firebase.", showSha1 = true)
            e is GetCredentialException -> LoginError("Google login failed: $raw", showSha1 = true)
            else -> LoginError("Google login failed: $raw")
        }
    }

    /** SHA-1 of the key that signed THIS installed APK. This exact value must be in Firebase. */
    @Suppress("DEPRECATION")
    fun appSha1(ctx: Context): String = try {
        val pm = ctx.packageManager
        val sigs = if (Build.VERSION.SDK_INT >= 28) {
            val info = pm.getPackageInfo(ctx.packageName, PackageManager.GET_SIGNING_CERTIFICATES)
            info.signingInfo?.apkContentsSigners
        } else {
            pm.getPackageInfo(ctx.packageName, PackageManager.GET_SIGNATURES).signatures
        }
        sigs?.firstOrNull()?.toByteArray()?.let { bytes ->
            MessageDigest.getInstance("SHA-1").digest(bytes).joinToString(":") { "%02X".format(it) }
        } ?: "unknown"
    } catch (e: Exception) {
        "unknown"
    }
}
