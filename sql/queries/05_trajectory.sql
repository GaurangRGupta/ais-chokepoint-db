-- Q5. Trajectory for the MMSI with the most stored positions in the last 6 hours.
-- Shape: mmsi, n_points, traj geography. Open geom in pgAdmin Geometry Viewer.

WITH pick AS (
    SELECT mmsi
    FROM ais.vessel_position
    WHERE valid_time >= clock_timestamp() - interval '6 hours'
    GROUP BY mmsi
    ORDER BY count(*) DESC
    LIMIT 1
)
SELECT
    p.mmsi,
    s.name,
    count(*) AS n_points,
    min(p.valid_time) AS t_from,
    max(p.valid_time) AS t_to,
    ST_MakeLine(p.geom::geometry ORDER BY p.valid_time)::geography AS traj
FROM ais.vessel_position p
JOIN pick ON pick.mmsi = p.mmsi
LEFT JOIN ais.vessel_static_current s ON s.mmsi = p.mmsi
WHERE p.valid_time >= clock_timestamp() - interval '6 hours'
GROUP BY p.mmsi, s.name;
