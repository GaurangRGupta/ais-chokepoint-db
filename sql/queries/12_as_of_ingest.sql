-- Q12. World time-slice at T versus what the database knew at the same clock time.
-- A late packet can have valid_time <= T but ingest_time > T, so it appears in
-- the world slice and not in the as-of-ingest slice.

WITH t AS (
    SELECT coalesce(
        (SELECT max(valid_time) FROM ais.vessel_position),
        clock_timestamp()
    ) - interval '10 minutes' AS t_cut
),
world AS (
    SELECT DISTINCT ON (p.mmsi)
        p.mmsi, p.valid_time, p.ingest_time, p.sog_kn
    FROM ais.vessel_position p
    CROSS JOIN t
    WHERE p.valid_time <= t.t_cut
      AND p.valid_time >= t.t_cut - interval '2 hours'
    ORDER BY p.mmsi, p.valid_time DESC
),
known AS (
    SELECT DISTINCT ON (p.mmsi)
        p.mmsi, p.valid_time, p.ingest_time, p.sog_kn
    FROM ais.vessel_position p
    CROSS JOIN t
    WHERE p.valid_time <= t.t_cut
      AND p.ingest_time <= t.t_cut
      AND p.valid_time >= t.t_cut - interval '2 hours'
    ORDER BY p.mmsi, p.valid_time DESC
)
SELECT
    coalesce(w.mmsi, k.mmsi) AS mmsi,
    w.valid_time AS world_valid_time,
    w.ingest_time AS world_ingest_time,
    k.valid_time AS known_valid_time,
    k.ingest_time AS known_ingest_time,
    (w.valid_time IS DISTINCT FROM k.valid_time) AS late_arrival
FROM world w
FULL OUTER JOIN known k ON k.mmsi = w.mmsi
ORDER BY late_arrival DESC, mmsi
LIMIT 50;
