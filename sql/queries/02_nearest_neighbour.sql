-- Q2. Five current vessels nearest to a fixed point in the strait (PostGIS <->).
-- Point is 1.20 N, 103.85 E (Main Strait / off St John's area).
-- Shape: mmsi, distance_m, lat, lon.

SELECT
    c.mmsi,
    round(ST_Distance(
        c.geom,
        ST_SetSRID(ST_MakePoint(103.85, 1.20), 4326)::geography
    )::numeric, 1) AS distance_m,
    ST_Y(c.geom::geometry) AS lat,
    ST_X(c.geom::geometry) AS lon,
    c.sog_kn,
    c.valid_time
FROM ais.vessel_position_current c
ORDER BY c.geom <-> ST_SetSRID(ST_MakePoint(103.85, 1.20), 4326)::geography
LIMIT 5;

-- EXPLAIN (ANALYZE, BUFFERS)
-- SELECT c.mmsi
-- FROM ais.vessel_position_current c
-- ORDER BY c.geom <-> ST_SetSRID(ST_MakePoint(103.85, 1.20), 4326)::geography
-- LIMIT 5;
