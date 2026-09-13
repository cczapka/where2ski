from where2ski_pipeline.geo import haversine_km, point_in_geometry, point_in_polygon


def test_haversine_munich_innsbruck():
    d = haversine_km(48.137, 11.575, 47.269, 11.404)
    assert 95 < d < 100


def test_point_in_polygon_square_and_hole():
    outer = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    hole = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]
    assert point_in_polygon(1, 1, [outer])
    assert not point_in_polygon(11, 1, [outer])
    assert not point_in_polygon(5, 5, [outer, hole])
    multi = {"type": "MultiPolygon", "coordinates": [[outer], [[[20, 20], [30, 20], [30, 30], [20, 30], [20, 20]]]]}
    assert point_in_geometry(25, 25, multi)
    assert not point_in_geometry(15, 15, multi)
