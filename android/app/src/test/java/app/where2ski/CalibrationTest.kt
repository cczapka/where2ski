package app.where2ski

import app.where2ski.data.Calibration
import app.where2ski.data.Mode
import app.where2ski.data.Scoring
import app.where2ski.data.TripRating
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CalibrationTest {

    private fun rating(date: String, stars: Int, fresh: Double, sun: Double) = TripRating(
        resortId = "r", resortName = "R", date = date, mode = Mode.FREERIDE.key, stars = stars,
        factors = mapOf(
            "fresh_snow" to fresh,
            "sun_vis" to sun,
            "snow_quality_freeride" to fresh,
            "travel" to 0.5,
        ),
    )

    /** Five days where the good ones were the snowy ones, regardless of sun. */
    private val powderLover = listOf(
        rating("2026-01-10", 5, fresh = 1.0, sun = 0.2),
        rating("2026-01-12", 4, fresh = 0.8, sun = 0.3),
        rating("2026-01-15", 3, fresh = 0.5, sun = 0.9),
        rating("2026-01-20", 2, fresh = 0.2, sun = 1.0),
        rating("2026-01-25", 1, fresh = 0.0, sun = 0.8),
    )

    @Test
    fun pearsonMatchesKnownValues() {
        assertEquals(1.0, Calibration.pearson(listOf(1.0, 2.0, 3.0), listOf(2.0, 4.0, 6.0)), 1e-9)
        assertEquals(-1.0, Calibration.pearson(listOf(1.0, 2.0, 3.0), listOf(3.0, 2.0, 1.0)), 1e-9)
        assertEquals(0.0, Calibration.pearson(listOf(1.0, 1.0, 1.0), listOf(1.0, 2.0, 3.0)), 1e-9)
        assertEquals(0.0, Calibration.pearson(listOf(1.0), listOf(1.0)), 1e-9)
    }

    @Test
    fun tooFewRatingsKeepsCurrentWeights() {
        val current = Scoring.defaultWeights.getValue(Mode.FREERIDE)
        val s = Calibration.suggest(powderLover.take(3), Mode.FREERIDE, current)
        assertTrue(!s.enoughData)
        assertEquals(current["fresh_snow"], s.weights["fresh_snow"])
    }

    @Test
    fun snowyDaysRatedHighRaiseTheSnowWeightAndLowerSun() {
        val current = Scoring.defaultWeights.getValue(Mode.FREERIDE)
        val s = Calibration.suggest(powderLover, Mode.FREERIDE, current)
        assertTrue(s.enoughData)
        val fresh = s.factors.single { it.key == "fresh_snow" }
        val sun = s.factors.single { it.key == "sun_vis" }
        assertTrue("fresh snow should correlate positively", fresh.correlation > 0.9)
        assertTrue("sun should correlate negatively here", sun.correlation < 0.0)
        assertTrue(fresh.suggestedWeight > fresh.currentWeight)
        assertTrue(sun.suggestedWeight < sun.currentWeight)
        assertTrue(s.weights.values.all { it in 0.0..30.0 })
    }

    @Test
    fun ratingsOfTheOtherModeAreIgnored() {
        val piste = powderLover.map { it.copy(mode = Mode.PISTE.key) }
        val s = Calibration.suggest(piste, Mode.FREERIDE, Scoring.defaultWeights.getValue(Mode.FREERIDE))
        assertEquals(0, s.ratings)
        assertTrue(!s.enoughData)
    }
}
