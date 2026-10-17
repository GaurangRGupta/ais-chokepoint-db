-- Q6. Traffic picture at time T in the world (valid_time), not merely the current table.
-- T is 10 minutes before the latest stored AIS event, so this works after ingest stops.
-- Shape: same idea as vessel_position_current, but as of T.

WITH t AS (
    SELECT coalesce(
        (SELECT max(valid_time) FROM ais.vessel_position),
        clock_timestamp()
    ) - interval '10 minutes' AS world_t
),
ranked AS (
    SELECT
        p.mmsi,
        p.geom,
        p.sog_kn,
        p.valid_time,
        p.ingest_time,
        row_number() OVER (PARTITION BY p.mmsi ORDER BY p.valid_time DESC) AS rn
    FROM ais.vessel_position p
    CROSS JOIN t
    WHERE p.valid_time <= t.world_t
      AND p.valid_time >= t.world_t - interval '2 hours'
)
SELECT
    r.mmsi,
    s.name,
    r.sog_kn,
    r.valid_time,
    r.ingest_time,
    ST_Y(r.geom::geometry) AS lat,
    ST_X(r.geom::geometry) AS lon
FROM ranked r
LEFT JOIN ais.vessel_static_current s ON s.mmsi = r.mmsi
WHERE r.rn = 1
ORDER BY r.valid_time DESC;
