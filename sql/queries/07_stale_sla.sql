-- Q7. Current positions with no fresh valid_time for more than 15 minutes (lost contact SLA).
-- After a live ingest this is often empty. Stop ingest, wait 15 minutes, run again.

SELECT
    c.mmsi,
    s.name,
    c.valid_time,
    round(extract(epoch from clock_timestamp() - c.valid_time)::numeric / 60, 1) AS age_min,
    c.sog_kn,
    ST_Y(c.geom::geometry) AS lat,
    ST_X(c.geom::geometry) AS lon
FROM ais.vessel_position_current c
LEFT JOIN ais.vessel_static_current s ON s.mmsi = c.mmsi
WHERE clock_timestamp() - c.valid_time > interval '15 minutes'
ORDER BY c.valid_time;
