package app.where2ski.ui

import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import app.where2ski.data.DayConditions
import app.where2ski.data.Latest
import app.where2ski.data.Mode
import app.where2ski.data.ResortConditions
import app.where2ski.data.Scoring
import app.where2ski.data.UserSettings

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DetailScreen(
    latest: Latest?,
    settings: UserSettings,
    resortId: String,
    selectedDay: Int,
    onSelectDay: (Int) -> Unit,
    onBack: () -> Unit,
) {
    val resort = latest?.resorts?.firstOrNull { it.id == resortId }
    Column(modifier = Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text(resort?.name ?: "Resort") },
            navigationIcon = {
                IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") }
            },
        )
        if (latest == null || resort == null) {
            Text("Resort not found.", modifier = Modifier.padding(16.dp))
        } else {
            DayChips(latest.days, selectedDay, onSelectDay)
            val day = latest.days.getOrNull(selectedDay)?.let { date -> resort.days.firstOrNull { it.date == date } }
            ResortDetails(resort, day, settings)
        }
    }
}

@Composable
private fun ResortDetails(resort: ResortConditions, day: DayConditions?, settings: UserSettings) {
    val context = LocalContext.current
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        Text(
            "${resort.elevation.base.toInt()}–${resort.elevation.top.toInt()} m · ${resort.region}" +
                (resort.travelMin?.let { " · $it min from Munich" } ?: "") +
                (if (resort.passes.isNotEmpty()) " · " + resort.passes.joinToString { passLabel(it) } else ""),
            style = MaterialTheme.typography.bodySmall,
        )
        if (day == null) {
            Text("No assessment for this day.", modifier = Modifier.padding(top = 12.dp))
        } else {
            DayDetails(resort, day, settings, onOpenLink = { url ->
                context.startActivity(Intent(Intent.ACTION_VIEW, url.toUri()))
            })
        }
    }
}

@Composable
private fun DayDetails(resort: ResortConditions, day: DayConditions, settings: UserSettings, onOpenLink: (String) -> Unit) {
    SectionTitle("Scores")
    Row(horizontalArrangement = Arrangement.spacedBy(16.dp), verticalAlignment = Alignment.CenterVertically) {
        Mode.entries.forEach { mode ->
            val score = Scoring.score(mode, day, settings.weights[mode] ?: Scoring.defaultWeights.getValue(mode))
            ScoreBadge(score)
            Column {
                Text(mode.label, style = MaterialTheme.typography.labelLarge)
                val blockers = day.blockers[mode.key].orEmpty()
                if (blockers.isNotEmpty()) {
                    Text(blockers.joinToString("; "), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                }
            }
        }
    }
    Text("confidence ${(day.confidence * 100).toInt()} %", style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 4.dp))
    if (day.badges.isNotEmpty()) {
        Text(day.badges.joinToString(" · ") { badgeLabel(it) }, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelLarge)
    }

    SectionTitle("Snow")
    KeyValue("Surface", stateLabel(day.snow.state) + (day.snow.aspect?.let { " (${it}-facing terrain)" } ?: ""))
    day.snow.bestAspect?.let { best ->
        val bs = day.snow.byAspect[best]
        if (bs != null) KeyValue("Best aspect", "$best · ${stateLabel(bs.state)} · ${(bs.share * 100).toInt()} % of terrain")
    }
    KeyValue("New snow 24 / 48 / 72 h", "${fmtCm(day.snow.hn24)} / ${fmtCm(day.snow.hn48)} / ${fmtCm(day.snow.hn72)}")
    KeyValue("Base depth", "${fmtCm(day.snow.hs)} (${day.snow.hsSource})")
    KeyValue("Days since snowfall", day.snow.daysSinceSnow?.let { "%.0f".format(it) } ?: "> 10")
    KeyValue("Hours above 0 °C since", day.snow.meltHours.toString())
    KeyValue("Melt-freeze cycles", day.snow.cycles.toString())
    day.snow.reasons.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall) }

    if (day.snow.byAspect.isNotEmpty()) {
        SectionTitle("Aspects")
        val terrain = resort.terrain
        Text(
            if (resort.aspectRose != null && terrain != null)
                "Terrain from OpenSkiMap: ${terrain.nRuns ?: 0} runs, ${"%.0f".format(terrain.runKm ?: 0.0)} km, ${terrain.elevP05 ?: 0}–${terrain.elevP95 ?: 0} m. Wedge length = share of terrain, colour = snow quality."
            else
                "No terrain data for this resort yet; all aspects are weighted equally. Colour = snow quality per aspect.",
            style = MaterialTheme.typography.bodySmall,
        )
        AspectRose(day.snow.byAspect, settings.mode, day.snow.bestAspect, modifier = Modifier.padding(vertical = 8.dp))
    }

    SectionTitle("Weather (mid mountain)")
    KeyValue("Sunshine", "%.1f h".format(day.weather.sunHours))
    KeyValue("Temperature min / max", "${fmtTemp(day.weather.tMinMid)} / ${fmtTemp(day.weather.tMaxMid)}")
    KeyValue("Daytime mean", fmtTemp(day.weather.tMeanDayMid))
    KeyValue("Gusts at top", day.weather.gustMaxTop?.let { "${it.toInt()} km/h" } ?: "–")
    KeyValue("Precipitation / snowfall", "%.1f mm / %.0f cm".format(day.weather.precipMm, day.weather.snowfallCm))
    KeyValue("Low cloud", day.weather.lowCloudPct?.let { "${it.toInt()} %" } ?: "–")
    KeyValue("Freezing level", day.weather.freezingLevelM?.let { "${it.toInt()} m" } ?: "–")

    SectionTitle("Avalanche")
    val av = day.avalanche
    if (av == null) {
        Text("No bulletin for this day (bulletins cover today and tomorrow).", style = MaterialTheme.typography.bodySmall)
    } else {
        KeyValue("Danger mid / top", "${av.levelMid ?: "–"} / ${av.levelTop ?: "–"}")
        av.tendency?.let { KeyValue("Tendency", it) }
        av.region?.let { KeyValue("Region", it) }
        av.problems.forEach { p ->
            Text("• ${p.type.replace('_', ' ')} ${p.elevation} ${p.aspects.joinToString("/")}", style = MaterialTheme.typography.bodySmall)
        }
    }

    SectionTitle("Factors")
    Scoring.factorKeys.forEach { key ->
        val v = Scoring.factorValue(settings.mode, day, key) ?: return@forEach
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 2.dp)) {
            Text(Scoring.labels[key] ?: key, style = MaterialTheme.typography.bodySmall, modifier = Modifier.width(130.dp))
            LinearProgressIndicator(progress = { v.toFloat() }, modifier = Modifier.weight(1f))
            Spacer(Modifier.width(8.dp))
            Text("%.2f".format(v), style = MaterialTheme.typography.bodySmall)
        }
    }

    resort.stationHistory?.let { h ->
        Text(
            "Melt and refreeze detection uses measurements from station ${h.station}" +
                (if (h.hasTss) " (snow-surface temperature)" else " (air temperature)") +
                (h.to?.let { " up to ${it.replace('T', ' ')}" } ?: ""),
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(top = 8.dp),
        )
    }
    if (resort.stations.isNotEmpty()) {
        SectionTitle("Nearby stations")
        resort.stations.forEach { s ->
            Text(
                "${s.name} (${s.elevation?.toInt() ?: "?"} m, ${s.distanceKm ?: "?"} km): HS ${fmtCm(s.hs)}, 24 h ${fmtCm(s.hn24)}, T ${fmtTemp(s.tAir)}" +
                    (s.tSurface?.let { ", surface ${fmtTemp(it)}" } ?: ""),
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }

    val bergfex = resort.link("bergfex")
    if (bergfex != null) {
        TextButton(onClick = { onOpenLink(bergfex) }) {
            Text("Open on Bergfex")
        }
    }
    Spacer(Modifier.padding(12.dp))
}
