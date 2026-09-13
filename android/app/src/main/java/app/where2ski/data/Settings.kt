package app.where2ski.data

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

data class UserSettings(
    val mode: Mode = Mode.FREERIDE,
    val weights: Map<Mode, Map<String, Double>> = Scoring.defaultWeights,
    val passFilter: Set<String> = emptySet(),
    val maxTravelMin: Int = 0,
) {
    val currentWeights: Map<String, Double> get() = weights[mode] ?: Scoring.defaultWeights.getValue(mode)
}

/** SharedPreferences-backed settings exposed as a StateFlow. */
class SettingsStore(context: Context) {
    private val prefs = context.getSharedPreferences("where2ski", Context.MODE_PRIVATE)
    private val _state = MutableStateFlow(load())
    val state: StateFlow<UserSettings> = _state

    private fun load(): UserSettings {
        val mode = Mode.fromKey(prefs.getString("mode", null))
        val weights = Mode.entries.associateWith { m ->
            Scoring.factorKeys.associateWith { key ->
                val default = Scoring.defaultWeights.getValue(m).getValue(key)
                prefs.getFloat("w_${m.key}_$key", default.toFloat()).toDouble()
            }
        }
        val passes = prefs.getStringSet("pass_filter", emptySet()).orEmpty().toSet()
        val travel = prefs.getInt("max_travel_min", 0)
        return UserSettings(mode, weights, passes, travel)
    }

    private fun save(s: UserSettings) {
        prefs.edit().apply {
            putString("mode", s.mode.key)
            for ((m, ws) in s.weights) for ((k, v) in ws) putFloat("w_${m.key}_$k", v.toFloat())
            putStringSet("pass_filter", s.passFilter)
            putInt("max_travel_min", s.maxTravelMin)
        }.apply()
        _state.value = s
    }

    fun setMode(mode: Mode) = save(_state.value.copy(mode = mode))

    fun setWeight(mode: Mode, key: String, value: Double) {
        val current = _state.value
        val updated = current.weights.toMutableMap()
        updated[mode] = current.weights.getValue(mode).toMutableMap().apply { put(key, value) }
        save(current.copy(weights = updated))
    }

    fun resetWeights(mode: Mode) {
        val current = _state.value
        val updated = current.weights.toMutableMap()
        updated[mode] = Scoring.defaultWeights.getValue(mode)
        save(current.copy(weights = updated))
    }

    fun setPassFilter(passes: Set<String>) = save(_state.value.copy(passFilter = passes))

    fun setMaxTravel(minutes: Int) = save(_state.value.copy(maxTravelMin = minutes))
}
