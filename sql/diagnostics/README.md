# Diagnostic SQL

Run these in pgAdmin Query Tool while connected to database `chokepoint`. They are read-only `SELECT` statements.

The explanations, architecture, attribute dictionaries, collection rates, and how to read each result grid are in [docs/dba-manual.md](../../docs/dba-manual.md).

| File | Purpose |
| --- | --- |
| `catalog.sql` | Inventory D1 to D32: databases, schemas, tables, columns, partitions, sizes, row counts, rates, lag, heartbeat, quality, roles |
| `one_ship.sql` | One MMSI: current row, history, trajectory, static versions, events. Edit the MMSI literal first. |

Open `catalog.sql`, press F5. pgAdmin shows one result grid per statement. Work through them in order. Start with D1, D10, D11, D16, and D17.

Do not paste passwords, connection strings, or API keys into the output you keep for the report.
