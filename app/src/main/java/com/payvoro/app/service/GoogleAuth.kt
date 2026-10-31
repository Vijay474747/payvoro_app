package com.payvoro.app.service

import android.app.Activity
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.payvoro.app.BuildConfig

/** Shows Google's account picker and returns an ID token. The server checks it. */
object GoogleAuth {
    suspend fun idToken(activity: Activity): Result<String> = try {
        val option = GetSignInWithGoogleOption.Builder(BuildConfig.GOOGLE_WEB_CLIENT_ID).build()
        val request = GetCredentialRequest.Builder().addCredentialOption(option).build()
        val cred = CredentialManager.create(activity).getCredential(activity, request).credential
        if (cred is CustomCredential && cred.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL)
            Result.success(GoogleIdTokenCredential.createFrom(cred.data).idToken)
        else Result.failure(Exception("Please choose a Google account"))
    } catch (e: GetCredentialCancellationException) {
        Result.failure(Exception("Login cancelled"))
    } catch (e: GetCredentialException) {
        Result.failure(Exception("Google login failed. Add a Google account to this phone (Settings → Accounts) and try again."))
    }
}
