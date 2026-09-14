package app.where2ski.data

/** A day worth telling the user about, picked from the published forecast. */
data class Alert(
    val resortId: String,
    val resortName: String,
    val date: String,
    val score: Double,
    val reason: String,
) {
    /** Stable id so the same day is not announced twice. */
    val key: String get() = "$resortId|$date|${reason}"
}

object Alerts {
    const val SCORE_THRESHOLD = 75.0
    const val LOOKAHEAD_DAYS = 5

    /**
     * The best upcoming day that is worth a notification: a powder day, or any
     * day scoring above the threshold under the user's own weights and filters.
     * Returns null when nothing stands out.
     */
    fun best(latest: Latest, settings: UserSettings, alreadyNotified: Set<String>): Alert? {
        val candidates = mutableListOf<Alert>()
        val days = latest.days.take(LOOKAHEAD_DAYS)
        for ((index, date) in days.withIndex()) {
            for (item in rank(latest, index, settings.mode, settings.currentWeights, settings.passFilter, settings.maxTravelMin)) {
                val day = item.day
                val powder = "powder_day" in day.badges
                if (!powder && item.score < SCORE_THRESHOLD) continue
                val reason = when {
                    powder && day.snow.hn48 >= 1.0 -> "${day.snow.hn48.toInt()} cm fresh snow"
                    powder -> "powder day"
                    else -> "score ${item.score.toInt()}"
                }
                val alert = Alert(item.resort.id, item.resort.name, date, item.score, reason)
                if (alert.key !in alreadyNotified) candidates.add(alert)
            }
        }
        return candidates.maxByOrNull { it.score }
    }

    /** Top resorts for a given day index, for the home-screen widget. */
    fun topForDay(latest: Latest, settings: UserSettings, dayIndex: Int, count: Int = 3): List<RankedResort> =
        rank(latest, dayIndex, settings.mode, settings.currentWeights, settings.passFilter, settings.maxTravelMin)
            .take(count)

    /** Index of the next Saturday in the published day list, or 0 if none is covered. */
    fun weekendIndex(latest: Latest): Int {
        val index = latest.days.indexOfFirst { date ->
            runCatching { java.time.LocalDate.parse(date).dayOfWeek == java.time.DayOfWeek.SATURDAY }.getOrDefault(false)
        }
        return if (index >= 0) index else 0
    }
}
