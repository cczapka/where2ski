package app.where2ski

import app.where2ski.data.DayConditions
import app.where2ski.data.Latest
import app.where2ski.data.Mode
import app.where2ski.data.Scoring
import app.where2ski.data.rank
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ScoringTest {
    private val json = Json { ignoreUnknownKeys = true; coerceInputValues = true }

    private val sample = """
        {
          "generated_at": "2026-01-15T06:00:00+00:00",
          "today": "2026-01-15",
          "days": ["2026-01-15", "2026-01-16"],
          "resorts": [
            {"id": "kuehtai", "name": "Kühtai", "region": "AT-07", "lat": 47.2, "lon": 11.0,
             "elevation": {"base": 2020, "mid": 2300, "top": 2520}, "passes": ["snowcard_tirol"], "travel_min": 120,
             "links": {"bergfex": "https://example.org", "season": {"open": "2025-12-01", "close": "2026-04-19"}},
             "stations": [], "error": null,
             "days": [
               {"date": "2026-01-15", "lead": 0, "scores": {"freeride": 90.0, "piste": 80.0},
                "blockers": {"freeride": [], "piste": []},
                "factors": {"fresh_snow": 1.0, "snow_quality_freeride": 1.0, "snow_quality_piste": 0.9, "avalanche": 0.8,
                            "sun_vis": 0.5, "wind": 1.0, "temperature": 1.0, "base": 1.0, "travel": 0.6, "crowd": 1.0},
                "confidence": 1.0, "badges": ["powder_day"],
                "snow": {"state": "fresh_powder", "hn24": 20, "hn48": 30, "hn72": 35, "hs": 120, "hs_source": "station",
                         "aspect": "N", "best_aspect": "S",
                         "by_aspect": {"N": {"share": 0.4, "state": "fresh_powder", "value_freeride": 0.2, "value_piste": 0.9, "capped": true},
                                       "S": {"share": 0.6, "state": "fresh_powder", "value_freeride": 1.0, "value_piste": 0.9, "capped": false}}},
                "weather": {"sun_hours": 4.0, "t_mean_day_mid": -6.0},
                "avalanche": {"level_mid": 2, "level_top": 3, "problems": [{"type": "wind_slab", "aspects": ["N"], "elevation": "above 2200 m"}]}},
               {"date": "2026-01-16", "lead": 1, "scores": {"freeride": 0.0, "piste": 70.0},
                "blockers": {"freeride": ["avalanche danger level 4"], "piste": []},
                "factors": {"fresh_snow": 0.2, "snow_quality_freeride": 0.3, "snow_quality_piste": 0.7, "avalanche": 0.0,
                            "sun_vis": 0.9, "wind": 0.8, "temperature": 1.0, "base": 1.0, "travel": 0.6, "crowd": 0.7},
                "confidence": 0.9, "badges": [], "snow": {"state": "hardpack"}, "weather": {"sun_hours": 7.0}, "avalanche": null}
             ]}
          ]
        }
    """.trimIndent()

    @Test
    fun decodesPipelineJson() {
        val latest = json.decodeFromString<Latest>(sample)
        val r = latest.resorts.single()
        assertEquals("Kühtai", r.name)
        assertEquals("https://example.org", r.link("bergfex"))
        assertEquals(120.0, r.days[0].snow.hs!!, 1e-9)
        assertEquals(3, r.days[0].avalanche?.levelTop)
        assertEquals("S", r.days[0].snow.bestAspect)
        assertEquals(true, r.days[0].snow.byAspect["N"]?.capped)
        assertEquals(0.6, r.days[0].snow.byAspect["S"]!!.share, 1e-9)
        assertEquals(null, r.days[1].avalanche)
    }

    @Test
    fun scoreMatchesWeightedAverageAndBlockers() {
        val latest = json.decodeFromString<Latest>(sample)
        val day0: DayConditions = latest.resorts[0].days[0]
        val freeride = Scoring.score(Mode.FREERIDE, day0, Scoring.defaultWeights.getValue(Mode.FREERIDE))
        // 25*1 + 25*1 + 20*0.8 + 10*0.5 + 5*1 + 5*1 + 5*0.6 + 5*1 = 89 over 100
        assertEquals(89.0, freeride, 1e-6)
        val blocked = Scoring.score(Mode.FREERIDE, latest.resorts[0].days[1], Scoring.defaultWeights.getValue(Mode.FREERIDE))
        assertEquals(0.0, blocked, 1e-9)
        val piste = Scoring.score(Mode.PISTE, latest.resorts[0].days[1], Scoring.defaultWeights.getValue(Mode.PISTE))
        assertTrue(piste > 60.0)
    }

    @Test
    fun rankingAppliesFilters() {
        val latest = json.decodeFromString<Latest>(sample)
        val all = rank(latest, 0, Mode.FREERIDE, Scoring.defaultWeights.getValue(Mode.FREERIDE), emptySet(), 0)
        assertEquals(1, all.size)
        val tooFar = rank(latest, 0, Mode.FREERIDE, Scoring.defaultWeights.getValue(Mode.FREERIDE), emptySet(), 90)
        assertTrue(tooFar.isEmpty())
        val wrongPass = rank(latest, 0, Mode.FREERIDE, Scoring.defaultWeights.getValue(Mode.FREERIDE), setOf("ski_amade"), 0)
        assertTrue(wrongPass.isEmpty())
    }
}
