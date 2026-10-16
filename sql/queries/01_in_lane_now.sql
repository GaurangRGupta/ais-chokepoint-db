-- Q1. Vessels whose current position is inside an eastbound or westbound TSS lane.
-- Shape: mmsi, name, sog_kn, lane, lon, lat.
-- Geometry: run this, then in pgAdmin right-click a geom column > View/Edit Data is not needed;
-- use the Geometry Viewer on a query that selects geom if you want a map screenshot.

SELECT
    c.mmsi,
    s.name,
    c.sog_kn,
    g.name AS lane,
    g.kind,
    ST_Y(c.geom::geometry) AS lat,
    ST_X(c.geom::geometry) AS lon,
    c.valid_time,
    c.geom
FROM ais.vessel_position_current c
JOIN ops.geofence g ON g.kind IN ('lane_east', 'lane_west')
    AND ST_Covers(g.geom, c.geom)
LEFT JOIN ais.vessel_static_current s ON s.mmsi = c.mmsi
ORDER BY g.kind, c.sog_kn DESC NULLS LAST;

-- EXPLAIN (ANALYZE, BUFFERS)
-- SELECT c.mmsi FROM ais.vessel_position_current c
-- JOIN ops.geofence g ON g.kind IN ('lane_east', 'lane_west') AND ST_Covers(g.geom, c.geom);
