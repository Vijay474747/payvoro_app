package com.payvoro.app.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.NavController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.payvoro.app.AppState
import com.payvoro.app.data.Payment
import com.payvoro.app.data.Prefs
import com.payvoro.app.service.Api
import com.payvoro.app.service.BackendSync
import com.payvoro.app.service.Perms
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { PayvoroTheme { PayvoroRoot() } }
    }
}

private data class Tab(val route: String, val label: String, val icon: ImageVector)

private val tabs = listOf(
    Tab("home", "Home", Icons.Filled.Home),
    Tab("history", "History", Icons.Filled.History),
    Tab("qr", "My QR", Icons.Filled.QrCode2),
    Tab("analytics", "Analytics", Icons.Filled.BarChart),
    Tab("profile", "Profile", Icons.Filled.Person),
)

fun NavController.goTab(route: String) = navigate(route) {
    popUpTo("home") { saveState = true }
    launchSingleTop = true
    restoreState = true
}

@Composable
fun PayvoroRoot() {
    val nav = rememberNavController()
    val ctx = LocalContext.current
    var alert by remember { mutableStateOf<Payment?>(null) }

    // Big full-screen alert when a payment arrives while the app is open
    LaunchedEffect(Unit) { AppState.events.collect { alert = it } }
    val route = nav.currentBackStackEntryAsState().value?.destination?.route

    // On app start: refresh plan + push payments saved while offline.
    // If the session was ended on the server (stopped / logged out), go back to login.
    LaunchedEffect(Unit) {
        val prefs = Prefs(ctx)
        if (prefs.loggedIn) {
            withContext(Dispatchers.IO) { Api.refreshMe(ctx); BackendSync.syncPending(ctx) }
            if (!prefs.loggedIn) nav.navigate("login") { popUpTo(nav.graph.id) { inclusive = true } }
        }
    }
    Scaffold(
        containerColor = Bg,
        bottomBar = {
            if (tabs.any { it.route == route }) NavigationBar(containerColor = androidx.compose.ui.graphics.Color.White) {
                tabs.forEach { t ->
                    NavigationBarItem(
                        selected = route == t.route,
                        onClick = { nav.goTab(t.route) },
                        icon = { Icon(t.icon, t.label) },
                        label = { Text(t.label) },
                        colors = NavigationBarItemDefaults.colors(selectedIconColor = Purple, selectedTextColor = Purple, indicatorColor = PurpleLight)
                    )
                }
            }
        }
    ) { pad ->
        NavHost(nav, startDestination = "splash", modifier = Modifier.padding(pad)) {
            composable("splash") { SplashScreen { next -> nav.navigate(next) { popUpTo("splash") { inclusive = true } } } }
            composable("login") {
                LoginScreen { nav.navigate(nextRoute(ctx)) { popUpTo("login") { inclusive = true } } }
            }
            composable("setup") {
                SetupScreen(onScan = { nav.navigate("scan") }) {
                    nav.navigate(nextRoute(ctx)) { popUpTo("setup") { inclusive = true } }
                }
            }
            // First plan: no back button. Home opens only after UPI AutoPay is set.
            composable("plans_first") {
                PlansScreen(firstTime = true, onBack = null) {
                    nav.navigate(nextRoute(ctx)) { popUpTo("plans_first") { inclusive = true } }
                }
            }
            composable("permissions") { PermissionScreen { nav.navigate("home") { popUpTo("permissions") { inclusive = true } } } }
            composable("home") { HomeScreen(nav) }
            composable("history") { HistoryScreen { nav.navigate("plans") } }
            composable("qr") { QrScreen { nav.navigate("scan") } }
            composable("scan") { QrScanScreen { nav.popBackStack() } }
            composable("plans") { PlansScreen(firstTime = false, onBack = { nav.popBackStack() }) { nav.popBackStack() } }
            composable("analytics") { AnalyticsScreen { nav.navigate("plans") } }
            composable("profile") { ProfileScreen(nav) }
            composable("apps") { AppsScreen { nav.popBackStack() } }
            composable("status") { StatusScreen { nav.popBackStack() } }
            composable("permissions_again") { PermissionScreen { nav.popBackStack() } }
        }
    }

    alert?.let { PaymentAlertDialog(it) { alert = null } }
}
