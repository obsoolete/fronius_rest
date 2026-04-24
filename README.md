# Fronius Gen24

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/obsoolete/fronius_rest.svg)](https://github.com/obsoolete/fronius_rest/releases)
[![License](https://img.shields.io/github/license/obsoolete/fronius_rest.svg)](LICENSE)

Home Assistant integration for the Fronius Gen24 inverter. Communicates locally over HTTP — no cloud required.

## Entities

| Entity | Type | Description |
|---|---|---|
| PV Enabled | Switch | Enables / disables PV generation on both MPPT channels |
| Export Limitation | Switch | Enables / disables the export soft-limit |
| Export Power Limit | Number | Sets the export soft-limit (0 – 20 000 W) |
| GEN24 Software Version | Sensor | Installed firmware version |
| Last Update | Sensor | Timestamp of the last successful poll |

The export power limit is remembered across restarts. Changes made while export is off are applied when it is turned back on.

## Installation

**HACS:** Add `https://github.com/obsoolete/fronius_rest` as a custom repository (category: Integration), install, then restart Home Assistant.

**Manual:** Copy `custom_components/fronius_rest` into your `<config>/custom_components/` directory and restart.

## Setup

Go to **Settings → Devices & Services → Add Integration → Fronius Gen24** and enter your inverter's IP address, username (`technician` or `customer`), password, and preferred poll interval.

> Write operations (switches, export limit) require the **Technician** role.

## Troubleshooting

```yaml
logger:
  logs:
    custom_components.fronius_rest: debug
```
