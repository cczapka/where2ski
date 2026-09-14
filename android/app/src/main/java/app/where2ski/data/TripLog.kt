package app.where2ski.data

import android.content.Context
import java.io.File
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/** One rated ski day, stored with the factor values the pipeline published for it. */
@Serializable
data class TripRating(
    val resortId: String,
    val resortName: String = "",
    val date: String,
    val mode: String = Mode.FREERIDE.key,
    val stars: Int,
    val chips: List<String> = emptyList(),
    val factors: Map<String, Double> = emptyMap(),
    val scoreAtTime: Double = 0.0,
    val ratedAt: Long = 0L,
)

@Serializable
private data class TripFile(val ratings: List<TripRating> = emptyList())

/** Condition chips offered after a day out; they describe what you actually found. */
object TripChips {
    val all = listOf("powder", "tracked out", "groomed hero snow", "crust", "slush", "icy", "flat light", "windy", "crowded")
}

/** Ratings persisted as JSON in the app's private storage. */
class TripLogStore(context: Context) {
    private val json = Json { ignoreUnknownKeys = true; prettyPrint = true }
    private val file = File(context.filesDir, "trips.json")
    private val _state = MutableStateFlow(load())
    val state: StateFlow<List<TripRating>> = _state

    private fun load(): List<TripRating> = runCatching {
        if (file.exists()) json.decodeFromString<TripFile>(file.readText()).ratings else emptyList()
    }.getOrDefault(emptyList())

    private fun persist(list: List<TripRating>) {
        runCatching { file.writeText(json.encodeToString(TripFile(list))) }
        _state.value = list
    }

    /** One rating per resort and day; rating again replaces the previous entry. */
    fun add(rating: TripRating) {
        val without = _state.value.filterNot { it.resortId == rating.resortId && it.date == rating.date }
        persist((without + rating).sortedByDescending { it.date })
    }

    fun remove(resortId: String, date: String) {
        persist(_state.value.filterNot { it.resortId == resortId && it.date == date })
    }

    fun ratingFor(resortId: String, date: String): TripRating? =
        _state.value.firstOrNull { it.resortId == resortId && it.date == date }
}
