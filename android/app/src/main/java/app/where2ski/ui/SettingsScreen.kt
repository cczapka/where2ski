package app.where2ski.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import app.where2ski.data.Calibration
import app.where2ski.data.Latest
import app.where2ski.data.Scoring
import app.where2ski.data.SettingsStore
import app.where2ski.data.TripLogStore
import app.where2ski.data.UserSettings

@Composable
fun SettingsScreen(latest: Latest?, settings: UserSettings, store: SettingsStore, trips: TripLogStore) {
    val ratings by trips.state.collectAsState()
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
    ) {
        SectionTitle("Mode")
        ModeToggle(settings.mode, store::setMode)

        SectionTitle("Weights for ${settings.mode.label}")
        Text(
            "Relative importance of each factor. Scores are recomputed on the phone from the published factor values.",
            style = MaterialTheme.typography.bodySmall,
        )
        Scoring.factorKeys.forEach { key ->
            val value = settings.currentWeights[key] ?: 0.0
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(Scoring.labels[key] ?: key, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.width(140.dp))
                Slider(
                    value = value.toFloat(),
                    onValueChange = { store.setWeight(settings.mode, key, it.toDouble()) },
                    valueRange = 0f..30f,
                    steps = 29,
                    modifier = Modifier.weight(1f),
                )
                Text("%.0f".format(value), modifier = Modifier.width(28.dp))
            }
        }
        TextButton(onClick = { store.resetWeights(settings.mode) }) { Text("Reset to defaults") }

        SectionTitle("Your ski days")
        val suggestion = remember(ratings, settings) {
            Calibration.suggest(ratings, settings.mode, settings.currentWeights)
        }
        if (!suggestion.enoughData) {
            Text(
                "Rate a day on a resort page after skiing it. After ${Calibration.MIN_RATINGS} rated " +
                    "${settings.mode.label.lowercase()} days the app can suggest weights that match what you " +
                    "actually enjoyed (${suggestion.ratings} so far).",
                style = MaterialTheme.typography.bodySmall,
            )
        } else {
            Text(
                "${suggestion.ratings} rated ${settings.mode.label.lowercase()} days. A factor that was high on " +
                    "the days you liked gets more weight.",
                style = MaterialTheme.typography.bodySmall,
            )
            suggestion.factors.filter { it.changed }.forEach { f ->
                KeyValue(
                    Scoring.labels[f.key] ?: f.key,
                    "${"%.0f".format(f.currentWeight)} → ${"%.0f".format(f.suggestedWeight)} (r = ${"%.2f".format(f.correlation)})",
                )
            }
            if (suggestion.factors.none { it.changed }) {
                Text("Your current weights already match your ratings.", style = MaterialTheme.typography.bodySmall)
            } else {
                TextButton(onClick = {
                    suggestion.weights.forEach { (key, value) -> store.setWeight(settings.mode, key, value) }
                }) { Text("Apply suggested weights") }
            }
        }
        ratings.take(5).forEach { r ->
            Text(
                "${r.date} · ${r.resortName} · ${"★".repeat(r.stars)}" +
                    (if (r.chips.isEmpty()) "" else " · " + r.chips.joinToString(", ")),
                style = MaterialTheme.typography.bodySmall,
            )
        }

        SectionTitle("Passes")
        val passes = remember(latest) { latest?.resorts?.flatMap { it.passes }?.distinct()?.sorted().orEmpty() }
        if (passes.isEmpty()) {
            Text("Load data first to see the available passes.", style = MaterialTheme.typography.bodySmall)
        } else {
            Text("Select passes to show only resorts they cover. None selected = all resorts.", style = MaterialTheme.typography.bodySmall)
            Row(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 4.dp),
            ) {
                passes.take(3).forEach { PassChip(it, settings, store) }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
                passes.drop(3).forEach { PassChip(it, settings, store) }
            }
        }

        SectionTitle("Maximum travel time")
        val travel = settings.maxTravelMin
        Text(if (travel <= 0) "No limit" else "$travel min from Munich", style = MaterialTheme.typography.bodyMedium)
        Slider(
            value = (if (travel <= 0) 240 else travel).toFloat(),
            onValueChange = { v -> store.setMaxTravel(if (v >= 240f) 0 else (v / 15f).toInt() * 15) },
            valueRange = 45f..240f,
            steps = 12,
        )

        SectionTitle("About")
        Text(
            "where2ski ranks resorts around Munich by snow and weather conditions. " +
                "Data is prepared by an open pipeline every three hours; this app only reads the result.",
            style = MaterialTheme.typography.bodySmall,
        )
        latest?.attribution?.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall) }
    }
}

@Composable
private fun PassChip(pass: String, settings: UserSettings, store: SettingsStore) {
    val selected = pass in settings.passFilter
    FilterChip(
        selected = selected,
        onClick = { store.setPassFilter(if (selected) settings.passFilter - pass else settings.passFilter + pass) },
        label = { Text(passLabel(pass)) },
    )
}
