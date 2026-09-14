package app.where2ski.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

/** Mirror of pipeline/out/latest.json. Unknown keys are ignored when decoding. */
@Serializable
data class Latest(
    @SerialName("generated_at") val generatedAt: String = "",
    val today: String = "",
    val days: List<String> = emptyList(),
    val weights: Map<String, Map<String, Double>> = emptyMap(),
    val attribution: List<String> = emptyList(),
    val resorts: List<ResortConditions> = emptyList(),
)

@Serializable
data class Elevation(val base: Double = 0.0, val mid: Double = 0.0, val top: Double = 0.0)

@Serializable
data class StationInfo(
    val name: String = "",
    val elevation: Double? = null,
    val hs: Double? = null,
    val hn24: Double? = null,
    val hn48: Double? = null,
    val hn72: Double? = null,
    @SerialName("t_air") val tAir: Double? = null,
    @SerialName("t_surface") val tSurface: Double? = null,
    val gust: Double? = null,
    val time: String? = null,
    @SerialName("distance_km") val distanceKm: Double? = null,
)

@Serializable
data class ResortConditions(
    val id: String,
    val name: String,
    val region: String = "",
    val lat: Double = 0.0,
    val lon: Double = 0.0,
    val elevation: Elevation = Elevation(),
    val passes: List<String> = emptyList(),
    @SerialName("travel_min") val travelMin: Int? = null,
    val glacier: Boolean = false,
    val links: JsonObject = JsonObject(emptyMap()),
    @SerialName("micro_region") val microRegion: String? = null,
    @SerialName("aspect_rose") val aspectRose: Map<String, Double>? = null,
    val terrain: TerrainInfo? = null,
    @SerialName("station_history") val stationHistory: StationHistoryInfo? = null,
    val stations: List<StationInfo> = emptyList(),
    val days: List<DayConditions> = emptyList(),
    val error: String? = null,
) {
    fun link(key: String): String? = links[key]?.let { runCatching { it.jsonPrimitive.contentOrNull }.getOrNull() }
}

@Serializable
data class DayConditions(
    val date: String,
    val lead: Int = 0,
    val scores: Map<String, Double> = emptyMap(),
    val blockers: Map<String, List<String>> = emptyMap(),
    val factors: Map<String, Double?> = emptyMap(),
    val confidence: Double = 0.0,
    val badges: List<String> = emptyList(),
    val snow: SnowInfo = SnowInfo(),
    val weather: WeatherInfo = WeatherInfo(),
    val avalanche: AvalancheInfo? = null,
)

@Serializable
data class TerrainInfo(
    @SerialName("elev_p05") val elevP05: Int? = null,
    @SerialName("elev_p95") val elevP95: Int? = null,
    @SerialName("run_km") val runKm: Double? = null,
    @SerialName("n_runs") val nRuns: Int? = null,
)

@Serializable
data class StationHistoryInfo(
    val station: String = "",
    val from: String? = null,
    val to: String? = null,
    @SerialName("has_tss") val hasTss: Boolean = false,
)

@Serializable
data class AspectState(
    val share: Double = 0.0,
    val state: String = "unknown",
    @SerialName("value_freeride") val valueFreeride: Double = 0.0,
    @SerialName("value_piste") val valuePiste: Double = 0.0,
    val capped: Boolean = false,
)

@Serializable
data class SnowInfo(
    val state: String = "unknown",
    val aspect: String? = null,
    @SerialName("best_aspect") val bestAspect: String? = null,
    @SerialName("by_aspect") val byAspect: Map<String, AspectState> = emptyMap(),
    val hn24: Double = 0.0,
    val hn48: Double = 0.0,
    val hn72: Double = 0.0,
    val hs: Double? = null,
    @SerialName("hs_source") val hsSource: String = "none",
    @SerialName("days_since_snow") val daysSinceSnow: Double? = null,
    @SerialName("melt_hours") val meltHours: Int = 0,
    val cycles: Int = 0,
    val refreeze: Boolean = false,
    @SerialName("rain_hours") val rainHours: Int = 0,
    val reasons: List<String> = emptyList(),
)

@Serializable
data class WeatherInfo(
    @SerialName("sun_hours") val sunHours: Double = 0.0,
    @SerialName("t_min_mid") val tMinMid: Double? = null,
    @SerialName("t_max_mid") val tMaxMid: Double? = null,
    @SerialName("t_mean_day_mid") val tMeanDayMid: Double? = null,
    @SerialName("gust_max_top") val gustMaxTop: Double? = null,
    @SerialName("precip_mm") val precipMm: Double = 0.0,
    @SerialName("snowfall_cm") val snowfallCm: Double = 0.0,
    @SerialName("low_cloud_pct") val lowCloudPct: Double? = null,
    @SerialName("freezing_level_m") val freezingLevelM: Double? = null,
)

@Serializable
data class AvalancheProblem(
    val type: String = "",
    val aspects: List<String> = emptyList(),
    val elevation: String = "",
)

@Serializable
data class AvalancheInfo(
    @SerialName("level_mid") val levelMid: Int? = null,
    @SerialName("level_top") val levelTop: Int? = null,
    val problems: List<AvalancheProblem> = emptyList(),
    val tendency: String? = null,
    val region: String? = null,
)
