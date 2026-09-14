package app.where2ski.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import app.where2ski.data.DayConditions
import app.where2ski.data.Mode
import app.where2ski.data.ResortConditions
import app.where2ski.data.Scoring
import app.where2ski.data.TripChips
import app.where2ski.data.TripRating

/**
 * Records how a ski day actually was. The factor values of that day are stored
 * with the rating, which is what makes the later weight calibration possible.
 */
@Composable
fun RateTripDialog(
    resort: ResortConditions,
    day: DayConditions,
    mode: Mode,
    existing: TripRating?,
    onDismiss: () -> Unit,
    onSave: (TripRating) -> Unit,
    onDelete: () -> Unit,
) {
    var stars by remember { mutableIntStateOf(existing?.stars ?: 3) }
    var chips by remember { mutableStateOf(existing?.chips?.toSet() ?: emptySet()) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("How was ${resort.name}?") },
        text = {
            Column {
                Text(dayLabel(day.date), style = MaterialTheme.typography.bodySmall)
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.fillMaxWidth()) {
                    (1..5).forEach { value ->
                        FilterChip(
                            selected = value <= stars,
                            onClick = { stars = value },
                            label = { Text("★") },
                        )
                    }
                }
                Text("What did you find?", style = MaterialTheme.typography.bodySmall)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    TripChips.all.forEach { chip ->
                        FilterChip(
                            selected = chip in chips,
                            onClick = { chips = if (chip in chips) chips - chip else chips + chip },
                            label = { Text(chip) },
                        )
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                onSave(
                    TripRating(
                        resortId = resort.id,
                        resortName = resort.name,
                        date = day.date,
                        mode = mode.key,
                        stars = stars,
                        chips = chips.toList(),
                        factors = day.factors.mapNotNull { (k, v) -> v?.let { k to it } }.toMap(),
                        scoreAtTime = Scoring.score(mode, day, Scoring.defaultWeights.getValue(mode)),
                        ratedAt = System.currentTimeMillis(),
                    ),
                )
            }) { Text("Save") }
        },
        dismissButton = {
            Row {
                if (existing != null) TextButton(onClick = onDelete) { Text("Delete") }
                TextButton(onClick = onDismiss) { Text("Cancel") }
            }
        },
    )
}
