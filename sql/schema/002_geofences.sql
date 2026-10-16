-- Operational geofences for the Singapore Strait live box.
-- Run in pgAdmin Query Tool on database chokepoint after 001_core.sql.
--
-- These are student operational sketches, not navigational charts.
-- Vertices follow published WGS 84 traffic-separation coordinates in
-- Maritime and Port Authority of Singapore, Singapore Port Information 2026,
-- Annex 5 (Main Strait), Annex 6 (Off St. John's Island), Annex 7
-- (Off Changi / Pulau Batam). That booklet cites IMO COLREG.2/Circ.44
-- (26 May 1998) and COLREG.2/Circ.54 (28 May 2004).
-- Western Anchorage is a box around the published representative point
-- for Western (AWW) in the same booklet (least-depth table).
-- The port-limit polygon is a simplified sketch of southern port waters
-- north of the TSS, for containment queries, not the official gazetted limit.
--
-- PostGIS polygons use (longitude latitude). Rings are closed.

INSERT INTO ops.geofence (name, kind, geom, drawn_by, notes)
VALUES (
    'tss_westbound',
    'lane_west',
    ST_GeogFromText(
        'SRID=4326;POLYGON((
            103.581667 1.172500,
            103.664167 1.172500,
            103.728667 1.125000,
            103.755500 1.143333,
            103.796833 1.171000,
            103.820000 1.180167,
            103.838833 1.187833,
            103.871667 1.203500,
            103.898833 1.216167,
            103.921667 1.226167,
            103.981833 1.248167,
            104.055000 1.261167,
            104.053667 1.276667,
            103.998333 1.267000,
            103.918000 1.234500,
            103.895833 1.223000,
            103.869167 1.208500,
            103.851833 1.199333,
            103.836833 1.193167,
            103.818000 1.185500,
            103.790000 1.174167,
            103.738333 1.144167,
            103.674167 1.191667,
            103.602333 1.210333,
            103.581667 1.172500
        ))'
    ),
    'adbms-group',
    'Westbound TSS lane. Outer edge points 95-99, 112-114, 128-131. Shared separator 85-87, 92-94, 110-111, 122-124, 126. MPA SPI 2026 Annex 5-7.'
)
ON CONFLICT (name) DO UPDATE SET
    geom = EXCLUDED.geom,
    kind = EXCLUDED.kind,
    notes = EXCLUDED.notes;

INSERT INTO ops.geofence (name, kind, geom, drawn_by, notes)
VALUES (
    'tss_eastbound',
    'lane_east',
    ST_GeogFromText(
        'SRID=4326;POLYGON((
            103.536667 1.100000,
            103.769167 1.130000,
            103.810000 1.157833,
            103.825833 1.165333,
            103.844167 1.174167,
            103.877667 1.190167,
            103.905000 1.201833,
            103.959500 1.225000,
            104.058000 1.234167,
            104.055000 1.261167,
            103.981833 1.248167,
            103.921667 1.226167,
            103.898833 1.216167,
            103.871667 1.203500,
            103.838833 1.187833,
            103.820000 1.180167,
            103.796833 1.171000,
            103.755500 1.143333,
            103.728667 1.125000,
            103.664167 1.172500,
            103.581667 1.172500,
            103.536667 1.100000
        ))'
    ),
    'adbms-group',
    'Eastbound TSS lane. Outer edge points 100 (clipped to 1.10 N), 103-105, 115-116, 132-134. Shared separator with westbound. MPA SPI 2026 Annex 5-7.'
)
ON CONFLICT (name) DO UPDATE SET
    geom = EXCLUDED.geom,
    kind = EXCLUDED.kind,
    notes = EXCLUDED.notes;

INSERT INTO ops.geofence (name, kind, geom, drawn_by, notes)
VALUES (
    'western_anchorage',
    'anchorage',
    ST_GeogFromText(
        'SRID=4326;POLYGON((
            103.780000 1.240000,
            103.830000 1.240000,
            103.830000 1.270000,
            103.780000 1.270000,
            103.780000 1.240000
        ))'
    ),
    'adbms-group',
    'Operational box around Western Anchorage (AWW) representative point 1 deg 15.141 min N, 103 deg 48.289 min E in MPA SPI 2026 least-depth table. Not the gazetted anchorage outline.'
)
ON CONFLICT (name) DO UPDATE SET
    geom = EXCLUDED.geom,
    kind = EXCLUDED.kind,
    notes = EXCLUDED.notes;

INSERT INTO ops.geofence (name, kind, geom, drawn_by, notes)
VALUES (
    'singapore_port_limit_sketch',
    'port_limit',
    ST_GeogFromText(
        'SRID=4326;POLYGON((
            103.650000 1.220000,
            103.850000 1.220000,
            104.050000 1.280000,
            104.050000 1.420000,
            103.650000 1.420000,
            103.650000 1.220000
        ))'
    ),
    'adbms-group',
    'Simplified southern port-waters sketch for containment queries. Not the official Singapore port limit.'
)
ON CONFLICT (name) DO UPDATE SET
    geom = EXCLUDED.geom,
    kind = EXCLUDED.kind,
    notes = EXCLUDED.notes;

SELECT name, kind,
       ST_IsValid(geom::geometry) AS is_valid,
       round(ST_Area(geom)::numeric, 0) AS area_m2
FROM ops.geofence
ORDER BY kind, name;
