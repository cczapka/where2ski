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
    "corn" -> "Corn snow"
    "crust" -> "Breakable crust"
    "hardpack" -> "Hardpack / old snow"
    "wet" -> "Wet / slush"
    "rain_soaked" -> "Rain-soaked"
    else -> state
}

fun badgeLabel(badge: String): String = when (badge) {
    "powder_day" -> "Powder day"
    "bluebird" -> "Bluebird"
    "inversion" -> "Sun above fog"
    "corn_morning" -> "Corn morning"
    "storm_skiing" -> "Storm skiing"
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
