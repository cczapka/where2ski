package app.where2ski.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Card
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.where2ski.data.Latest
import app.where2ski.data.Mode
import app.where2ski.data.RankedResort
import app.where2ski.data.UserSettings
import app.where2ski.data.rank

@Composable
fun RankingScreen(
    latest: Latest?,
    settings: UserSettings,
    loading: Boolean,
    error: String?,
    selectedDay: Int,
    onSelectDay: (Int) -> Unit,
    onSetMode: (Mode) -> Unit,
    onRefresh: () -> Unit,
    onOpenResort: (String) -> Unit,
) {
    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            ModeToggle(settings.mode, onSetMode)
            Spacer(Modifier.weight(1f))
            IconButton(onClick = onRefresh) { Icon(Icons.Filled.Refresh, contentDescription = "Refresh") }
        }
        if (loading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        if (error != null) {
            Text(
                "Could not load data: $error",
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(horizontal = 12.dp),
            )
        }
        if (latest == null) {
            Text(
                if (loading) "Loading conditions…" else "No data yet. Pull the latest data with the refresh button.",
                modifier = Modifier.padding(16.dp),
            )
        } else {
            RankingList(latest, settings, selectedDay, onSelectDay, onOpenResort)
        }
    }
}

@Composable
private fun RankingList(
    latest: Latest,
    settings: UserSettings,
    selectedDay: Int,
    onSelectDay: (Int) -> Unit,
    onOpenResort: (String) -> Unit,
) {
    DayChips(latest.days, selectedDay, onSelectDay)
    val ranked = remember(latest, settings, selectedDay) {
        rank(latest, selectedDay, settings.mode, settings.currentWeights, settings.passFilter, settings.maxTravelMin)
    }
    Text(
        "${settings.mode.label} · ${latest.days.getOrNull(selectedDay)?.let(::dayLabel) ?: ""} · data ${latest.generatedAt.take(16).replace('T', ' ')} UTC",
        style = MaterialTheme.typography.labelSmall,
        modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp),
    )
    LazyColumn(
        contentPadding = PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(ranked, key = { it.resort.id }) { item ->
            RankingCard(item, settings.mode) { onOpenResort(item.resort.id) }
        }
    }
}

@Composable
private fun RankingCard(item: RankedResort, mode: Mode, onClick: () -> Unit) {
    val d = item.day
    val blockers = d.blockers[mode.key].orEmpty()
    Card(modifier = Modifier
        .fillMaxWidth()
        .clickable(onClick = onClick)) {
        Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            ScoreBadge(item.score)
            Spacer(Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(item.resort.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                val line1 = buildString {
                    append(stateLabel(d.snow.state))
                    append(" · new ${fmtCm(d.snow.hn24)} / 72 h ${fmtCm(d.snow.hn72)}")
                    if (d.snow.hs != null) append(" · base ${fmtCm(d.snow.hs)}")
                }
                Text(line1, style = MaterialTheme.typography.bodySmall)
                val line2 = buildString {
                    append("sun ${"%.0f".format(d.weather.sunHours)} h · ${fmtTemp(d.weather.tMeanDayMid)}")
                    d.weather.gustMaxTop?.let { append(" · gusts ${it.toInt()} km/h") }
                    d.avalanche?.levelTop?.let { append(" · danger $it") }
                    item.resort.travelMin?.let { append(" · ${it} min") }
                }
                Text(line2, style = MaterialTheme.typography.bodySmall)
                if (blockers.isNotEmpty()) {
                    Text(
                        blockers.joinToString("; "),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                } else if (d.badges.isNotEmpty()) {
                    Text(
                        d.badges.joinToString(" · ") { badgeLabel(it) },
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }
        }
    }
}
