-- Q4. Open anchorage dwells (end_time is null).
-- Run uv run adbms-events first. A dwell needs 15 minutes inside with SOG under 0.5 kn.
-- Shape: mmsi, anchorage, duration so far, min_sog, median_sog.

SELECT
    d.mmsi,
    s.name,
    g.name AS anchorage,
    d.start_time,
    round(extract(epoch from clock_timestamp() - d.start_time)::numeric / 60, 1) AS duration_min,
    d.min_sog,
    d.median_sog
FROM ops.dwell_event d
JOIN ops.geofence g ON g.geofence_id = d.geofence_id
LEFT JOIN ais.vessel_static_current s ON s.mmsi = d.mmsi
WHERE d.end_time IS NULL
ORDER BY d.start_time;
