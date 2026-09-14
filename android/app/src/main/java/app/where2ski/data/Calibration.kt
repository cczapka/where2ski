package app.where2ski.data

import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.sqrt

/**
 * Turns rated ski days into a weight suggestion.
 *
 * For each factor it correlates the factor value with the stars given. A factor
 * that was high on the days you enjoyed and low on the days you did not gets
 * more weight; one that shows no relation keeps roughly its current weight.
 * Deliberately simple and explainable: with a handful of ski days per season a
 * fitted regression would mostly fit noise.
 */
object Calibration {
    const val MIN_RATINGS = 5

    data class FactorSuggestion(
        val key: String,
        val correlation: Double,
        val currentWeight: Double,
        val suggestedWeight: Double,
        val samples: Int,
    ) {
        val changed: Boolean get() = abs(suggestedWeight - currentWeight) >= 1.0
    }

    data class Suggestion(
        val mode: Mode,
        val ratings: Int,
        val factors: List<FactorSuggestion>,
    ) {
        val enoughData: Boolean get() = ratings >= MIN_RATINGS
        val weights: Map<String, Double> get() = factors.associate { it.key to it.suggestedWeight }
    }

    fun pearson(xs: List<Double>, ys: List<Double>): Double {
        if (xs.size < 2 || xs.size != ys.size) return 0.0
        val mx = xs.average()
        val my = ys.average()
        var num = 0.0
        var dx = 0.0
        var dy = 0.0
        for (i in xs.indices) {
            val a = xs[i] - mx
            val b = ys[i] - my
            num += a * b
            dx += a * a
            dy += b * b
        }
        if (dx <= 1e-9 || dy <= 1e-9) return 0.0
        return (num / sqrt(dx * dy)).coerceIn(-1.0, 1.0)
    }

    fun suggest(ratings: List<TripRating>, mode: Mode, current: Map<String, Double>): Suggestion {
        val relevant = ratings.filter { it.mode == mode.key }
        val factors = Scoring.factorKeys.map { key ->
            val lookup = if (key == "snow_quality") "snow_quality_${mode.key}" else key
            val pairs = relevant.mapNotNull { r -> r.factors[lookup]?.let { it to r.stars.toDouble() } }
            val base = current[key] ?: Scoring.defaultWeights.getValue(mode).getValue(key)
            val corr = if (pairs.size >= MIN_RATINGS) pearson(pairs.map { it.first }, pairs.map { it.second }) else 0.0
            val suggested = if (pairs.size >= MIN_RATINGS) {
                ((base * (1.0 + corr)).coerceIn(0.0, 30.0) * 1.0).roundToInt().toDouble()
            } else {
                base
            }
            FactorSuggestion(key, corr, base, suggested, pairs.size)
        }
        return Suggestion(mode, relevant.size, factors)
    }
}
