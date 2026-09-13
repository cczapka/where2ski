package app.where2ski.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument

private data class Tab(val route: String, val label: String, val icon: ImageVector)

private val tabs = listOf(
    Tab("ranking", "Ranking", Icons.Filled.List),
    Tab("matrix", "Matrix", Icons.Filled.DateRange),
    Tab("map", "Map", Icons.Filled.Place),
    Tab("settings", "Settings", Icons.Filled.Settings),
)

@Composable
fun Where2skiApp(vm: MainViewModel = viewModel()) {
    val nav = rememberNavController()
    val backStack by nav.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route

    val latest by vm.latest.collectAsState()
    val settings by vm.settings.state.collectAsState()
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()
    val selectedDay by vm.selectedDay.collectAsState()

    Scaffold(
        bottomBar = {
            NavigationBar {
                tabs.forEach { tab ->
                    NavigationBarItem(
                        selected = currentRoute == tab.route,
                        onClick = {
                            nav.navigate(tab.route) {
                                popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(tab.icon, contentDescription = tab.label) },
                        label = { Text(tab.label) },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(nav, startDestination = "ranking", modifier = Modifier.padding(padding)) {
            composable("ranking") {
                RankingScreen(
                    latest = latest, settings = settings, loading = loading, error = error,
                    selectedDay = selectedDay,
                    onSelectDay = vm::selectDay,
                    onSetMode = vm.settings::setMode,
                    onRefresh = vm::refresh,
                    onOpenResort = { id -> nav.navigate("resort/$id") },
                )
            }
            composable("matrix") {
                MatrixScreen(
                    latest = latest, settings = settings, selectedDay = selectedDay,
                    onSelectDay = vm::selectDay,
                    onOpenResort = { id -> nav.navigate("resort/$id") },
                )
            }
            composable("map") {
                MapScreen(
                    latest = latest, settings = settings, selectedDay = selectedDay,
                    onSelectDay = vm::selectDay,
                    onOpenResort = { id -> nav.navigate("resort/$id") },
                )
            }
            composable("settings") {
                SettingsScreen(latest = latest, settings = settings, store = vm.settings)
            }
            composable(
                "resort/{id}",
                arguments = listOf(navArgument("id") { type = NavType.StringType }),
            ) { entry ->
                val id = entry.arguments?.getString("id").orEmpty()
                DetailScreen(
                    latest = latest, settings = settings, resortId = id, selectedDay = selectedDay,
                    onSelectDay = vm::selectDay,
                    onBack = { nav.popBackStack() },
                )
            }
        }
    }
}
