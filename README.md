# Fronius Gen24 — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/obsoolete/fronius_rest.svg)](https://github.com/obsoolete/fronius_rest/releases)
[![License](https://img.shields.io/github/license/obsoolete/fronius_rest.svg)](LICENSE)

A Home Assistant custom integration for the **Fronius Gen24** solar inverter, using the local HTTP REST API with SHA-256 Digest Authentication. No cloud dependency — everything communicates directly with the inverter on your LAN.

---

## Features

| Entity | Type | Description |
|---|---|---|
| **PV Enabled** | Switch | Enables / disables PV generation on both MPPT channels |
| **Export Limitation** | Switch | Enables / disables the active-power export soft-limit |
| **Export Power Limit** | Number | Sets the export soft-limit in Watts (0 – 20 000 W) |
| **GEN24 Software Version** | Sensor | Reports the installed GEN24 firmware string |
| **Last Update** | Sensor | Timestamp of the last successful inverter poll |

### Behaviour highlights

- **Export Power Limit** always shows the configured value even when the limit is off — the last-used value is remembered across Home Assistant restarts.
- Changing the limit while export is off saves it locally; it is applied to the inverter the next time Export Limitation is enabled.
- Optimistic entity updates mean the UI responds immediately without waiting for the next poll cycle.

---

## Prerequisites

- A **Fronius Gen24** inverter reachable on the local network via HTTP.
- **Technician credentials** for the inverter web interface. The Customer role can read state but cannot toggle switches or write settings.

---

## Installation

### Via HACS (recommended)

1. Open HACS in Home Assistant.
2. Go to **Integrations → ⋮ → Custom repositories**.
3. Add `https://github.com/obsoolete/fronius_rest` with category **Integration**.
4. Search for **Fronius Gen24** and install it.
5. Restart Home Assistant.

### Manual

1. Download or clone this repository.
2. Copy the `custom_components/fronius_rest` folder into your `<config>/custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration

After installation, add the integration via **Settings → Devices & Services → Add Integration → Fronius Gen24**.

| Field | Description |
|---|---|
| **Host or IP address** | IP or hostname of the inverter (e.g. `192.168.1.100`) |
| **Username** | `technician` or `customer` (Technician required for write operations) |
| **Password** | The password set on the inverter web interface |
| **Poll interval** | How often to poll the inverter, in seconds (5 – 120, default 30) |

The poll interval can be changed later via **Settings → Devices & Services → Fronius Gen24 → Configure**.

---

## Notes

- The integration uses **HTTP only** (not HTTPS). Ensure your inverter is accessible on `http://`.
- All write operations require the **Technician** role. If you log in as Customer, the switches and number entity will raise an error when you try to change them.
- The `Export Power Limit` entity accepts `0 W` to fully suppress export without disabling the limitation feature.
- The `hardLimit` on the inverter is intentionally left disabled (`enabled: false`, `powerLimit: 0`); only the `softLimit` is managed by this integration.

---

## Troubleshooting

Enable debug logging by adding the following to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.fronius_rest: debug
```

Then reload the integration and check the Home Assistant logs.

---

## License

MIT — see [LICENSE](LICENSE).
