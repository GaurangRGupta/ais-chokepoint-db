# Deploy files

`ais-ingest.service` is the systemd unit for the always-on ingest worker on `vm-ais-ingest`.

Click-by-click: [docs/ingest-vm.md](../docs/ingest-vm.md).

Do not put secrets in this folder. The unit reads `/etc/ais-chokepoint.env` on the virtual machine.
