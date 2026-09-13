package app.where2ski.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import app.where2ski.data.Latest
import app.where2ski.data.Scoring
import app.where2ski.data.UserSettings

@Composable
fun MatrixScreen(
    latest: Latest?,
    settings: UserSettings,
    selectedDay: Int,
    onSelectDay: (Int) -> Unit,
    onOpenResort: (String) -> Unit,
) {
    if (latest == null) {
        Text("No data yet.", modifier = Modifier.padding(16.dp))
        return
    }
    val rows = remember(latest, settings) {
        latest.resorts
            .filter { it.error == null }
            .filter { settings.passFilter.isEmpty() || it.passes.any { p -> p in settings.passFilter } }
            .filter { settings.maxTravelMin <= 0 || (it.travelMin ?: 0) <= settings.maxTravelMin }
            .map { r ->
                r to latest.days.map { date ->
                    r.days.firstOrNull { it.date == date }?.let { Scoring.score(settings.mode, it, settings.currentWeights) }
                }
            }
            .sortedByDescending { (_, scores) -> scores.getOrNull(selectedDay) ?: -1.0 }
    }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .horizontalScroll(rememberScrollState())
            .padding(8.dp),
    ) {
        Text(
            "${settings.mode.label} scores per day. Tap a day header to sort by it, a name to open the resort.",
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(bottom = 6.dp),
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("", modifier = Modifier.width(120.dp))
            latest.days.forEachIndexed { index, date ->
                Text(
                    if (index == 0) "Today" else dayLabel(date),
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier
                        .width(44.dp)
                        .clickable { onSelectDay(index) },
                    color = if (index == selectedDay) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
                )
            }
        }
        rows.forEach { (resort, scores) ->
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(2.dp),
                modifier = Modifier.padding(vertical = 2.dp),
            ) {
                Text(
                    resort.name,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier
                        .width(118.dp)
                        .clickable { onOpenResort(resort.id) },
                )
                scores.forEach { s ->
                    if (s == null) Text("–", modifier = Modifier.width(42.dp)) else ScoreBadge(s, Modifier.width(42.dp), size = 36)
                }
            }
        }
    }
}
