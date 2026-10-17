-- Q5. Trajectory for the MMSI with the most stored history points.
-- Shape: mmsi, n_points, traj geography. Open traj in pgAdmin Geometry Viewer.
-- Uses the whole history table so a laptop overnight gap does not empty the result.
-- Needs at least two points for one MMSI. The current table is not a path.

SELECT
    (SELECT count(*) FROM ais.vessel_position) AS positions,
    (SELECT count(*) FROM ais.vessel_position_current) AS current_ships,
    (SELECT min(valid_time) FROM ais.vessel_position) AS min_valid_time,
    (SELECT max(valid_time) FROM ais.vessel_position) AS max_valid_time,
    clock_timestamp() AS db_now;

WITH pick AS (
    SELECT mmsi
    FROM ais.vessel_position
    GROUP BY mmsi
    HAVING count(*) >= 2
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
GROUP BY p.mmsi, s.name;
