# AIS chokepoint database

Advanced Database Management Systems group project. Three student database administrators run a live vessel-traffic database for the Singapore Strait.

Ships send Automatic Identification System (AIS) positions. The database stores those positions with valid time (when the fact was true in the world) and ingest time (when we learned it). It answers who is in a traffic lane now, who transited recently, who is sitting in an anchorage, where a vessel went between two times, what the picture looked like at time T, and whose position has gone stale.

No forecasting. No product UI. pgAdmin plus query evidence is the demo surface.

## Stack

- Python 3.12, managed with uv
- Azure as the only cloud data plane
- Azure Database for PostgreSQL Flexible Server with PostGIS
- Azure Blob Storage as the raw landing zone (rebuild and demo-day replay)
- A small Linux virtual machine that keeps the AIS WebSocket ingest running

AWS student credits stay unused unless Azure credit is exhausted.

## Local setup

```powershell
cd adbms_project
uv sync
uv run adbms-project
```

Secrets (AISStream key, Open Waters token, database password) live in environment variables or a local `.env` file. They are not committed. `internal_documents/` is also gitignored.

## Azure

You provision the cloud resources yourself. Follow [docs/azure-setup.md](docs/azure-setup.md). It has portal clicks and Azure CLI commands, student-credit checks, SKU choices, firewall rules, and PostGIS enablement.

Do not open PostgreSQL to the whole internet. Do not pick a General Purpose database SKU. Do not upgrade the student subscription to pay as you go for this course.

## Day-1 feed spike

Needs `AISSTREAM_API_KEY` in `.env`. Open Waters is automatic backup after 5 minutes of silence.

```powershell
cd adbms_project
uv sync --group dev
uv run adbms-spike
```

Default is 10 minutes on the Singapore Strait box. The report is `reports/day1_spike.md` (no secrets).

```powershell
uv run pytest
```

## Laptop ingest

Needs `AISSTREAM_API_KEY`, `DATABASE_URL`, and blob auth in `.env`. Click-by-click: [docs/ingest.md](docs/ingest.md).

```powershell
cd adbms_project
uv sync --group dev
uv run adbms-ingest --duration 180
```

Raw frames land in blob `ais-raw` at `raw/ais/yyyy/mm/dd/hh.jsonl.gz`. Validated rows go into `ais.vessel_position` and `ais.vessel_static_current`. Bad coordinates, impossible speed, and future timestamps go to `ais.quarantine`.

## Database administrator manual

Inventory, architecture, attribute dictionaries, collection rates, and diagnostic SQL: [docs/dba-manual.md](docs/dba-manual.md).

In pgAdmin, connect to database `chokepoint`, open `sql/diagnostics/catalog.sql`, press F5. One result grid per statement (D1 to D32). For a single ship, edit the MMSI in `sql/diagnostics/one_ship.sql`.

## Geofences and queries

Load `sql/schema/002_geofences.sql`, then run the files in `sql/queries/`. Click-by-click: [docs/geofences.md](docs/geofences.md).

```powershell
uv run adbms-ingest
uv run adbms-events
```

## Always-on ingest virtual machine

The laptop cannot stay on. Put the worker on Ubuntu virtual machine `vm-ais-ingest` in Central India. Click-by-click: [docs/ingest-vm.md](docs/ingest-vm.md). systemd unit: `deploy/ais-ingest.service`.

You create the virtual machine yourself in the portal or with Azure CLI. Stop laptop ingest after the unit is healthy.

## Status

PostgreSQL Flexible Server, PostGIS 3.6, schema `001_core.sql`, blob container `ais-raw`, laptop ingest, DBA manual, and diagnostic catalogue are up. The day-1 spike passed on Singapore. Next: create `vm-ais-ingest` and run the worker under systemd ([docs/ingest-vm.md](docs/ingest-vm.md)). Keep capturing Q1 to Q12 in pgAdmin while ingest is live.
