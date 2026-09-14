package app.where2ski.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import app.where2ski.MainActivity
import app.where2ski.R
import app.where2ski.data.Alerts
import app.where2ski.data.Latest
import app.where2ski.data.SettingsStore
import java.io.File
import kotlin.math.roundToInt
import kotlinx.serialization.json.Json

/** Home-screen widget: the best three resorts for the coming weekend. */
class BestDaysWidget : AppWidgetProvider() {

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val pending = goAsync()
        try {
            val views = buildViews(context)
            ids.forEach { manager.updateAppWidget(it, views) }
        } finally {
            pending.finish()
        }
    }

    companion object {
        private val rowIds = intArrayOf(R.id.widget_row_1, R.id.widget_row_2, R.id.widget_row_3)

        fun updateAll(context: Context) {
            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, BestDaysWidget::class.java))
            if (ids.isEmpty()) return
            val views = buildViews(context)
            ids.forEach { manager.updateAppWidget(it, views) }
        }

        private fun cached(context: Context): Latest? = runCatching {
            val file = File(context.filesDir, "latest.json")
            if (!file.exists()) return null
            Json { ignoreUnknownKeys = true; coerceInputValues = true }.decodeFromString<Latest>(file.readText())
        }.getOrNull()

        private fun buildViews(context: Context): RemoteViews {
            val views = RemoteViews(context.packageName, R.layout.widget_best)
            views.setOnClickPendingIntent(
                R.id.widget_root,
                PendingIntent.getActivity(
                    context, 0, Intent(context, MainActivity::class.java),
                    PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
                ),
            )
            val latest = cached(context)
            if (latest == null) {
                views.setTextViewText(R.id.widget_title, "where2ski")
                views.setTextViewText(R.id.widget_row_1, "Open the app to load conditions")
                views.setTextViewText(R.id.widget_row_2, "")
                views.setTextViewText(R.id.widget_row_3, "")
                return views
            }
            val settings = SettingsStore(context).state.value
            val index = Alerts.weekendIndex(latest)
            val date = latest.days.getOrNull(index).orEmpty()
            val top = Alerts.topForDay(latest, settings, index, rowIds.size)
            views.setTextViewText(R.id.widget_title, "${settings.mode.label} · ${date.takeLast(5)}")
            rowIds.forEachIndexed { i, id ->
                val item = top.getOrNull(i)
                views.setTextViewText(
                    id,
                    if (item == null) "" else "${item.score.roundToInt()}  ${item.resort.name}",
                )
            }
            return views
        }
    }
}
