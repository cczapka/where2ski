package app.where2ski.ui

import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToInt

private val dayFormatter: DateTimeFormatter = DateTimeFormatter.ofPattern("EEE d.M.", Locale.GERMAN)

fun dayLabel(isoDate: String): String =
    runCatching { LocalDate.parse(isoDate).format(dayFormatter) }.getOrDefault(isoDate)

fun fmtCm(v: Double?): String = if (v == null) "–" else "${v.roundToInt()} cm"

fun fmtTemp(v: Double?): String = if (v == null) "–" else "${v.roundToInt()} °C"

fun fmtScore(v: Double): String = v.roundToInt().toString()

fun stateLabel(state: String): String = when (state) {
    "fresh_powder" -> "Fresh powder"
    "wind_affected" -> "Wind-affected powder"
    "settled_powder" -> "Settled powder"
    "corn" -> "Corn snow, softened"
    "crust" -> "Breakable crust"
    "hardpack" -> "Hardpack / old snow"
    "wet" -> "Wet / slush"
    "rain_soaked" -> "Rain-soaked"
    "dust_on_crust" -> "Dust on crust"
    "moist" -> "Moist new snow"
    "rain_crust" -> "Rain crust"
    "corn_frozen" -> "Corn, still frozen"
    else -> state
}

fun badgeLabel(badge: String): String = when (badge) {
    "powder_day" -> "Powder day"
    "bluebird" -> "Bluebird"
    "inversion" -> "Sun above fog"
    "corn_morning" -> "Corn morning"
    "storm_skiing" -> "Storm skiing"
    "limited_opening" -> "Limited opening"
    else -> badge
}

fun passLabel(pass: String): String = when (pass) {
    "snowcard_tirol" -> "Snow Card Tirol"
    "ski_amade" -> "Ski amadé"
    "alpin_card" -> "Alpin Card"
    "alpen_plus" -> "Alpen Plus"
    "garmisch" -> "Garmisch"
    "oberstdorf_kleinwalsertal" -> "Oberstdorf/Kleinwalsertal"
    else -> pass
}

fun hsSourceLabel(source: String): String = when (source) {
    "station" -> "measured"
    "station+forecast" -> "measured, plus forecast snowfall"
    "model" -> "weather model, not measured"
    "none" -> "unknown"
    else -> source
}

fun fmtAge(hours: Double?): String = when {
    hours == null -> "time unknown"
    hours < 1.0 -> "${(hours * 60).roundToInt()} min ago"
    hours < 48.0 -> "${hours.roundToInt()} h ago"
    else -> "${(hours / 24).roundToInt()} days ago"
}

fun ruleLabel(rule: String): String = when (rule) {
    "stale" -> "reading too old"
    "limit" -> "outside 0–600 cm"
    "limit_24h" -> "jump of more than 150 cm in 24 h"
    "agreement" -> "large new snow not confirmed by another station"
    "continuity" -> "jump against yesterday without precipitation"
    "bare_ground" -> "sensor reads bare ground (warm, no modelled snow)"
    "excluded" -> "station excluded for this resort"
    else -> rule
}

fun underLabel(under: String?): String = when (under) {
    "crust" -> "on a crust"
    "ice" -> "on ice (rain crust)"
    "firm" -> "on a firm base"
    else -> ""
}
