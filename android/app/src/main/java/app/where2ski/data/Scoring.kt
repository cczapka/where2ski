package app.where2ski.data

enum class Mode(val key: String, val label: String) {
    FREERIDE("freeride", "Freeride"),
    PISTE("piste", "Piste");

    companion object {
        fun fromKey(key: String?): Mode = entries.firstOrNull { it.key == key } ?: FREERIDE
    }
}

/** Weighted score from the factor values shipped in latest.json; mirrors the pipeline formula. */
object Scoring {
    val factorKeys = listOf(
        "fresh_snow", "snow_quality", "avalanche", "sun_vis", "wind", "temperature", "base", "travel", "crowd",
        "roads",
    )

    val labels = mapOf(
        "fresh_snow" to "Fresh snow",
        "snow_quality" to "Snow quality",
        "avalanche" to "Avalanche safety",
        "sun_vis" to "Sun & visibility",
        "wind" to "Wind",
        "temperature" to "Temperature",
        "base" to "Base depth",
        "travel" to "Travel time",
        "crowd" to "Crowds",
        "roads" to "Roads on the way",
    )

    val defaultWeights: Map<Mode, Map<String, Double>> = mapOf(
        Mode.FREERIDE to mapOf(
            "fresh_snow" to 25.0, "snow_quality" to 25.0, "avalanche" to 20.0, "sun_vis" to 10.0,
            "wind" to 5.0, "temperature" to 5.0, "base" to 0.0, "travel" to 5.0, "crowd" to 5.0, "roads" to 5.0,
        ),
        Mode.PISTE to mapOf(
            "fresh_snow" to 15.0, "snow_quality" to 15.0, "avalanche" to 0.0, "sun_vis" to 30.0,
            "wind" to 10.0, "temperature" to 10.0, "base" to 10.0, "travel" to 5.0, "crowd" to 5.0, "roads" to 5.0,
        ),
    )

    fun factorValue(mode: Mode, day: DayConditions, key: String): Double? {
        val fkey = if (key == "snow_quality") "snow_quality_${mode.key}" else key
        return day.factors[fkey]
    }

    fun score(mode: Mode, day: DayConditions, weights: Map<String, Double>): Double {
        if (day.blockers[mode.key].orEmpty().isNotEmpty()) return 0.0
        var total = 0.0
        var wsum = 0.0
        for ((key, w) in weights) {
            if (w <= 0.0) continue
            val v = factorValue(mode, day, key) ?: continue
            total += w * v
            wsum += w
        }
        return if (wsum > 0.0) 100.0 * total / wsum else 0.0
    }
}

data class RankedResort(val resort: ResortConditions, val day: DayConditions, val score: Double)

fun rank(
    latest: Latest,
    dayIndex: Int,
    mode: Mode,
    weights: Map<String, Double>,
    passFilter: Set<String>,
    maxTravelMin: Int,
): List<RankedResort> {
    val date = latest.days.getOrNull(dayIndex) ?: return emptyList()
    return latest.resorts.asSequence()
        .filter { it.error == null }
        .filter { passFilter.isEmpty() || it.passes.any { p -> p in passFilter } }
        .filter { maxTravelMin <= 0 || (it.travelMin ?: 0) <= maxTravelMin }
        .mapNotNull { r ->
            val day = r.days.firstOrNull { it.date == date } ?: return@mapNotNull null
            RankedResort(r, day, Scoring.score(mode, day, weights))
        }
        .sortedByDescending { it.score }
        .toList()
}
