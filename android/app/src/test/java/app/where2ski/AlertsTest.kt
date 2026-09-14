package app.where2ski

import app.where2ski.data.Alerts
import app.where2ski.data.Latest
import app.where2ski.data.Mode
import app.where2ski.data.UserSettings
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AlertsTest {
    private val json = Json { ignoreUnknownKeys = true; coerceInputValues = true }

    /**
     * Two resorts on 2026-01-16. "good" is the one worth a notification; how
     * good it is comes from its factor values and badges, because the alert
     * logic recomputes the score under the user's own weights rather than
     * trusting the score the pipeline published.
     */
    private fun latest(goodFactor: Double, badges: String): Latest = json.decodeFromString(
        """
        {
          "today": "2026-01-15",
          "days": ["2026-01-15", "2026-01-16", "2026-01-17"],
          "resorts": [
            {"id": "good", "name": "Good", "lat": 47.0, "lon": 11.0, "passes": ["snowcard_tirol"], "travel_min": 100,
             "elevation": {"base": 1000, "mid": 1500, "top": 2000}, "error": null, "days": [
               {"date": "2026-01-16", "lead": 1, "scores": {"freeride": 0.0, "piste": 0.0},
                "blockers": {"freeride": [], "piste": []},
                "factors": {"fresh_snow": $goodFactor, "snow_quality_freeride": $goodFactor,
                            "snow_quality_piste": $goodFactor, "avalanche": $goodFactor, "sun_vis": $goodFactor,
                            "wind": $goodFactor, "temperature": $goodFactor, "base": $goodFactor,
                            "travel": $goodFactor, "crowd": $goodFactor, "roads": $goodFactor},
                "confidence": 0.9, "badges": [$badges],
                "snow": {"state": "fresh_powder", "hn48": 30.0}, "weather": {"sun_hours": 6.0}}
             ]},
            {"id": "dull", "name": "Dull", "lat": 47.5, "lon": 12.0, "passes": ["ski_amade"], "travel_min": 200,
             "elevation": {"base": 1000, "mid": 1500, "top": 2000}, "error": null, "days": [
               {"date": "2026-01-16", "lead": 1, "scores": {"freeride": 0.0, "piste": 0.0},
                "blockers": {"freeride": [], "piste": []},
                "factors": {"fresh_snow": 0.2, "snow_quality_freeride": 0.2, "snow_quality_piste": 0.2,
                            "avalanche": 0.8, "sun_vis": 0.3, "wind": 0.8, "temperature": 0.9, "base": 0.5,
                            "travel": 0.2, "crowd": 1.0, "roads": 1.0},
                "confidence": 0.9, "badges": [],
                "snow": {"state": "hardpack"}, "weather": {"sun_hours": 2.0}}
             ]}
          ]
        }
        """.trimIndent(),
    )

    private val powderDay = latest(goodFactor = 1.0, badges = "\"powder_day\"")
    private val quietDay = latest(goodFactor = 0.3, badges = "")

    @Test
    fun powderDayIsAnnouncedWithTheAmountOfSnow() {
        val alert = Alerts.best(powderDay, UserSettings(), emptySet())
        assertEquals("good", alert?.resortId)
        assertEquals("2026-01-16", alert?.date)
        assertEquals("30 cm fresh snow", alert?.reason)
        assertTrue((alert?.score ?: 0.0) > 90.0)
    }

    @Test
    fun aHighScoringDayWithoutABadgeStillCounts() {
        val alert = Alerts.best(latest(goodFactor = 1.0, badges = ""), UserSettings(), emptySet())
        assertNotNull(alert)
        assertTrue(alert!!.reason.startsWith("score "))
    }

    @Test
    fun alreadyAnnouncedDaysAreNotRepeated() {
        val first = Alerts.best(powderDay, UserSettings(), emptySet())!!
        assertNull(Alerts.best(powderDay, UserSettings(), setOf(first.key)))
    }

    @Test
    fun mediocreDaysProduceNothing() {
        assertNull(Alerts.best(quietDay, UserSettings(), emptySet()))
    }

    @Test
    fun filteredOutResortsAreNotAnnounced() {
        val onlyAmade = UserSettings(passFilter = setOf("ski_amade"))
        assertNull(Alerts.best(powderDay, onlyAmade, emptySet()))
        val nearbyOnly = UserSettings(maxTravelMin = 60)
        assertNull(Alerts.best(powderDay, nearbyOnly, emptySet()))
    }

    @Test
    fun widgetShowsTheTopResortsOfTheDay() {
        val top = Alerts.topForDay(powderDay, UserSettings(), 1, 3)
        assertEquals(listOf("good", "dull"), top.map { it.resort.id })
        assertTrue(top.first().score > top.last().score)
        // 2026-01-17 is a Saturday, index 2 in the published day list
        assertEquals(2, Alerts.weekendIndex(powderDay))
    }

    @Test
    fun theScoreInTheAlertFollowsTheSelectedMode() {
        val freeride = Alerts.best(powderDay, UserSettings(mode = Mode.FREERIDE), emptySet())!!
        val piste = Alerts.best(powderDay, UserSettings(mode = Mode.PISTE), emptySet())!!
        // all factors are 1.0 here, so both modes score full marks; the mode must still be honoured
        assertEquals(100.0, freeride.score, 0.01)
        assertEquals(100.0, piste.score, 0.01)
        val mixed = Alerts.best(quietDay, UserSettings(mode = Mode.PISTE), emptySet())
        assertNull(mixed)
    }
}
