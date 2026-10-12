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

## Status

Phase 0 is the day-1 AIS feed spike (local, before schema). Azure Session A (resource group and storage) can happen in parallel. Database and virtual machine wait until you are ready to keep them on.
