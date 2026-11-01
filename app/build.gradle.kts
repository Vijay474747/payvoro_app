import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.google.devtools.ksp")
}

// Firebase: only used when app/google-services.json is present.
// It also checks that the package name in that file is "com.payvoro.app" (build fails if not).
if (file("google-services.json").exists()) {
    apply(plugin = "com.google.gms.google-services")
} else {
    logger.warn("Payvoro: app/google-services.json not found – using GOOGLE_WEB_CLIENT_ID below.")
}

android {
    namespace = "com.payvoro.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.payvoro.app"
        minSdk = 24          // Android 7.0 and newer – covers almost every phone in use
        targetSdk = 34
        versionCode = 2
        versionName = "2.0.0"

        // DEMO MODE: login works without Google and without the server.
        // Plans (with AutoPay) turn on instantly. Set to false when your server is live.
        // ⚠ Must be "false" to test real Google login.
        buildConfigField("Boolean", "DEMO_MODE", "false")

        // "false" = show the "Choose plan" page after shop setup, with a "Skip for now" button.
        // "true"  = never show it (plans open only from Home → Upgrade Plan).
        buildConfigField("Boolean", "SKIP_PLAN_PAGE", "false")

        // Google login: only needed if you do NOT use Firebase's google-services.json.
        // With google-services.json the app takes the Web client ID from that file by itself.
        // Use the SAME Web client ID on the server (GOOGLE_WEB_CLIENT_ID on Vercel). See README.
        buildConfigField("String", "GOOGLE_WEB_CLIENT_ID", "\"YOUR_WEB_CLIENT_ID.apps.googleusercontent.com\"")
    }

    // ---- Signing: makes the APK installable on every phone ----
    // Your own key is read from keystore.properties (create it with make-keystore.sh).
    // If that file is missing, the release APK is signed with the debug key so it still installs –
    // fine for testing, but create your own key before giving the app to merchants.
    val keystoreFile = rootProject.file("keystore.properties")
    val keystoreProps = Properties().apply { if (keystoreFile.exists()) keystoreFile.inputStream().use { load(it) } }
    signingConfigs {
        if (keystoreFile.exists()) {
            create("release") {
                storeFile = rootProject.file(keystoreProps.getProperty("storeFile"))
                storePassword = keystoreProps.getProperty("storePassword")
                keyAlias = keystoreProps.getProperty("keyAlias")
                keyPassword = keystoreProps.getProperty("keyPassword")
                enableV1Signing = true      // older phones
                enableV2Signing = true      // newer phones
            }
        }
    }

    buildTypes {
        debug {
            // Debug builds also use the live Vercel server, so the Run button works on a real phone.
            // (For a server on your own PC: "http://10.0.2.2:8000" on the emulator, or your Wi-Fi IP on a phone.)
            buildConfigField("String", "SERVER_URL", "\"https://payvoro.vercel.app\"")
            manifestPlaceholders["cleartext"] = "true"
        }
        release {
            isMinifyEnabled = false
            signingConfig = if (keystoreFile.exists()) signingConfigs.getByName("release") else signingConfigs.getByName("debug")
            buildConfigField("String", "SERVER_URL", "\"https://payvoro.vercel.app\"")   // ← your Vercel URL (Vercel → Project → Domains)
            manifestPlaceholders["cleartext"] = "false"
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.09.00")
    implementation(composeBom)

    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.5")
    implementation("androidx.lifecycle:lifecycle-process:2.8.5")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.navigation:navigation-compose:2.8.0")

    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    ksp("androidx.room:room-compiler:2.6.1")

    implementation("com.google.zxing:core:3.5.3")

    // Camera for scanning the merchant's existing QR
    val camerax = "1.3.4"
    implementation("androidx.camera:camera-camera2:$camerax")
    implementation("androidx.camera:camera-lifecycle:$camerax")
    implementation("androidx.camera:camera-view:$camerax")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    // Google login (Credential Manager)
    implementation("androidx.credentials:credentials:1.3.0")
    implementation("androidx.credentials:credentials-play-services-auth:1.3.0")
    implementation("com.google.android.libraries.identity.googleid:googleid:1.1.1")

    testImplementation("junit:junit:4.13.2")
}
