-- Q11. Static identity versions (name, type, destination) with valid_range.
-- Empty until a ship reports two different static payloads. Re-run after hours of ingest.

SELECT
    h.mmsi,
    h.name,
    h.ship_type,
    h.destination,
    h.valid_range,
    h.ingest_time,
    h.source
FROM ais.vessel_static_history h
WHERE h.mmsi IN (
    SELECT mmsi
    FROM ais.vessel_static_history
    GROUP BY mmsi
    HAVING count(*) > 1
)
ORDER BY h.mmsi, lower(h.valid_range);

SELECT count(*) AS static_current FROM ais.vessel_static_current;
SELECT count(*) AS static_history FROM ais.vessel_static_history;
