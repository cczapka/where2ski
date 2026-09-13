package app.where2ski.ui

import android.graphics.drawable.GradientDrawable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import app.where2ski.data.Latest
import app.where2ski.data.UserSettings
import app.where2ski.data.rank
import java.io.File
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker

@Composable
fun MapScreen(
    latest: Latest?,
    settings: UserSettings,
    selectedDay: Int,
    onSelectDay: (Int) -> Unit,
    onOpenResort: (String) -> Unit,
) {
    val context = LocalContext.current
    val mapView = remember {
        Configuration.getInstance().apply {
            userAgentValue = context.packageName
            osmdroidBasePath = File(context.cacheDir, "osmdroid")
            osmdroidTileCache = File(context.cacheDir, "osmdroid/tiles")
        }
        MapView(context).apply {
            setTileSource(TileSourceFactory.MAPNIK)
            setMultiTouchControls(true)
            controller.setZoom(7.8)
            controller.setCenter(GeoPoint(47.35, 11.7))
        }
    }
    DisposableEffect(mapView) {
        mapView.onResume()
        onDispose { mapView.onPause() }
    }
    Column(modifier = Modifier.fillMaxSize()) {
        if (latest != null) DayChips(latest.days, selectedDay, onSelectDay)
        Text(
            "Marker colour = ${settings.mode.label} score. Tap a marker for the name and score.",
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp),
        )
        AndroidView(
            factory = { mapView },
            modifier = Modifier.fillMaxSize(),
            update = { map ->
                map.overlays.clear()
                if (latest != null) {
                    val ranked = rank(latest, selectedDay, settings.mode, settings.currentWeights, settings.passFilter, settings.maxTravelMin)
                    val px = (16 * context.resources.displayMetrics.density).toInt()
                    ranked.forEach { item ->
                        val marker = Marker(map)
                        marker.position = GeoPoint(item.resort.lat, item.resort.lon)
                        marker.setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
                        marker.title = item.resort.name
                        marker.snippet = "${settings.mode.label} ${fmtScore(item.score)} · ${stateLabel(item.day.snow.state)} · new ${fmtCm(item.day.snow.hn24)}"
                        marker.icon = GradientDrawable().apply {
                            shape = GradientDrawable.OVAL
                            setColor(scoreColor(item.score).toArgb())
                            setStroke(3, android.graphics.Color.WHITE)
                            setSize(px, px)
                        }
                        marker.setOnMarkerClickListener { m, _ ->
                            if (m.isInfoWindowShown) onOpenResort(item.resort.id) else m.showInfoWindow()
                            true
                        }
                        map.overlays.add(marker)
                    }
                }
                map.invalidate()
            },
        )
    }
}
