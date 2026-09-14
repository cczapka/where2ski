package app.where2ski.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import app.where2ski.data.AspectState
import app.where2ski.data.Mode
import kotlin.math.max

private val ORDER = listOf("N", "NE", "E", "SE", "S", "SW", "W", "NW")

/** Eight wedges: length = share of terrain facing that way, colour = snow value for the mode. */
@Composable
fun AspectRose(byAspect: Map<String, AspectState>, mode: Mode, bestAspect: String?, modifier: Modifier = Modifier) {
    val outline = MaterialTheme.colorScheme.outline
    val onSurface = MaterialTheme.colorScheme.onSurface
    val maxShare = max(0.05, byAspect.values.maxOfOrNull { it.share } ?: 0.125)
    Row(modifier = modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Canvas(modifier = Modifier.size(150.dp)) {
            val c = Offset(size.width / 2f, size.height / 2f)
            val r = size.minDimension / 2f * 0.92f
            drawCircle(color = outline, radius = r, center = c, style = Stroke(width = 1.5f))
            drawCircle(color = outline, radius = r / 2f, center = c, style = Stroke(width = 1f))
            ORDER.forEachIndexed { i, a ->
                val st = byAspect[a] ?: return@forEachIndexed
                val value = if (mode == Mode.FREERIDE) st.valueFreeride else st.valuePiste
                val len = (st.share / maxShare).toFloat().coerceIn(0.08f, 1f) * r
                val startAngle = -90f + i * 45f - 22.5f
                val color = scoreColor(value * 100.0)
                drawArc(
                    color = color,
                    startAngle = startAngle + 1.5f,
                    sweepAngle = 45f - 3f,
                    useCenter = true,
                    topLeft = Offset(c.x - len, c.y - len),
                    size = Size(len * 2, len * 2),
                )
                if (st.capped) {
                    drawArc(
                        color = Color.Black.copy(alpha = 0.55f),
                        startAngle = startAngle + 1.5f,
                        sweepAngle = 45f - 3f,
                        useCenter = true,
                        topLeft = Offset(c.x - len, c.y - len),
                        size = Size(len * 2, len * 2),
                        style = Stroke(width = 4f),
                    )
                }
            }
            drawLine(onSurface, Offset(c.x, c.y - r), Offset(c.x, c.y - r + 10f), strokeWidth = 3f)
        }
        Spacer(Modifier.width(12.dp))
        Column {
            ORDER.forEach { a ->
                val st = byAspect[a] ?: return@forEach
                val marker = if (a == bestAspect) "★ " else ""
                val capped = if (st.capped) " · avalanche problem" else ""
                Text(
                    "$marker$a ${(st.share * 100).toInt()} % · ${stateLabel(st.state)}$capped",
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(vertical = 1.dp),
                )
            }
        }
    }
}
