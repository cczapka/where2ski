package app.where2ski.work

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.Constraints
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import app.where2ski.MainActivity
import app.where2ski.R
import app.where2ski.data.Alerts
import app.where2ski.data.Repository
import app.where2ski.data.SettingsStore
import app.where2ski.widget.BestDaysWidget
import java.util.concurrent.TimeUnit

/** Refreshes the published forecast in the background, updates the widget and alerts on good days. */
class RefreshWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val context = applicationContext
        val latest = Repository(context).refresh().getOrElse { return Result.retry() }
        BestDaysWidget.updateAll(context)

        val settings = SettingsStore(context).state.value
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val notified = prefs.getStringSet(KEY_NOTIFIED, emptySet()).orEmpty()
        val alert = Alerts.best(latest, settings, notified) ?: return Result.success()

        notify(context, alert.resortName, "${alert.date}: ${alert.reason}, ${settings.mode.label} score ${alert.score.toInt()}")
        // keep the last 50 keys so an alert is announced once, but old ones can recur next season
        prefs.edit().putStringSet(KEY_NOTIFIED, (notified + alert.key).toList().takeLast(50).toSet()).apply()
        return Result.success()
    }

    private fun notify(context: Context, title: String, text: String) {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, "Good ski days", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "Alerts when conditions look good at one of your resorts"
            },
        )
        val intent = PendingIntent.getActivity(
            context, 0, Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val notification = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setContentIntent(intent)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(NOTIFICATION_ID, notification)
    }

    companion object {
        private const val PREFS = "where2ski_alerts"
        private const val KEY_NOTIFIED = "notified_keys"
        private const val CHANNEL = "conditions"
        private const val NOTIFICATION_ID = 1
        const val UNIQUE_WORK = "where2ski-refresh"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<RefreshWorker>(6, TimeUnit.HOURS)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork(UNIQUE_WORK, ExistingPeriodicWorkPolicy.KEEP, request)
        }
    }
}
