from tools.terrain import Accumulator, bearing_deg, sector


def test_bearing_and_sector():
    assert abs(bearing_deg(47.0, 11.0, 47.01, 11.0) - 0.0) < 1e-6      # due north
    assert abs(bearing_deg(47.0, 11.0, 47.0, 11.01) - 90.0) < 0.1      # due east
    assert sector(0) == "N" and sector(44) == "NE" and sector(180) == "S" and sector(350) == "N"


def test_accumulator_descent_direction_and_rose():
    acc = Accumulator()
    # a run descending from north to south: the slope faces south
    acc.add_run([[11.0, 47.01, 2000], [11.0, 47.005, 1900], [11.0, 47.0, 1800]], "Südhang")
    # a run drawn uphill from a low northern point to a high southern point: it descends northward, so it faces north
    acc.add_run([[11.1, 47.005, 1500], [11.1, 47.0, 1600]], "Nordhang")
    # a flat traverse contributes length but no aspect
    acc.add_run([[11.2, 47.0, 1500], [11.2, 47.0005, 1500.2]], "Ziehweg")
    res = acc.result()
    assert res["n_runs"] == 3
    assert res["aspect_rose"]["S"] > 0.6 and res["aspect_rose"]["N"] > 0.3
    assert abs(sum(res["aspect_rose"].values()) - 1.0) < 1e-6
    assert res["elev_min"] == 1500 and res["elev_max"] == 2000
    assert res["run_km"] > 1.5


def test_accumulator_ignores_runs_without_elevation():
    acc = Accumulator()
    acc.add_run([[11.0, 47.0], [11.0, 47.01]], "no z")
    assert acc.result() is None


def test_band_points_split_run_length_into_thirds():
    acc = Accumulator()
    # one straight run from 2400 m (north) down to 1500 m (south), equal segments
    coords = [[11.0, 47.0 + 0.003 * i, 1500 + 100 * i] for i in range(10)]
    acc.add_run(coords, "long")
    pts = acc.result()["points"]
    assert pts["base"][2] < pts["mid"][2] < pts["top"][2]
    assert 1550 <= pts["base"][2] <= 1700 and 2250 <= pts["top"][2] <= 2350
    assert pts["base"][0] < pts["top"][0]  # the lower third lies further south
