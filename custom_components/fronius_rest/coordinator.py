"""DataUpdateCoordinator for the Fronius Gen24 REST integration."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_POWER_LIMITS,
    API_POWERUNIT,
    API_VERSION,
    CONF_LAST_EXPORT_LIMIT,
    CONF_SCAN_INTERVAL,
    DATA_EXPORT_ENABLED,
    DATA_EXPORT_POWER_LIMIT,
    DATA_LAST_UPDATE,
    DATA_PV_ENABLED,
    DATA_SW_VERSION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    REQUEST_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

# Key under which the coordinator is stored in hass.data
CONF_HOST = "host"


def _parse_digest_challenge(challenge: str) -> dict[str, str]:
    """Parse a Digest auth challenge header into a parameter dict."""
    params: dict[str, str] = {}
    # Strip leading 'Digest ' prefix if present.
    if challenge.lower().startswith("digest "):
        challenge = challenge[7:]
    for item in challenge.split(","):
        item = item.strip()
        if "=" not in item:
            continue
        key, _, value = item.partition("=")
        params[key.strip()] = value.strip().strip('"')
    return params


def _compute_digest_auth(
    method: str,
    uri: str,
    username: str,
    password: str,
    params: dict[str, str],
) -> str:
    """Compute and return a Digest Authorization header value."""
    realm = params.get("realm", "")
    nonce = params.get("nonce", "")
    qop = params.get("qop", "auth")
    nc = "00000001"
    cnonce = secrets.token_hex(8)

    ha1 = hashlib.sha256(f"{username}:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.sha256(f"{method.upper()}:{uri}".encode()).hexdigest()
    response_hash = hashlib.sha256(
        f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}".encode()
    ).hexdigest()

    return (
        f'Digest username="{username}", realm="{realm}", nonce="{nonce}", '
        f'uri="{uri}", response="{response_hash}", qop={qop}, nc={nc}, cnonce="{cnonce}"'
    )


class FroniusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for the Fronius Gen24 REST API."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialise the coordinator."""
        scan_interval = int(
            config_entry.options.get(
                CONF_SCAN_INTERVAL,
                config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            )
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(seconds=scan_interval),
        )

        host = config_entry.data[CONF_HOST].rstrip("/")
        if not host.startswith("http://"):
            host = f"http://{host}"
        self.base_url: str = host
        self.username: str = config_entry.data[CONF_USERNAME]
        self.password: str = config_entry.data[CONF_PASSWORD]
        self.session = async_get_clientsession(hass)
        self._request_lock = asyncio.Lock()
        self._device_name: str = "Fronius Gen24"
        self._serial_number: str | None = None
        self._sw_version: str | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this inverter."""
        identifier = self._serial_number or self.config_entry.entry_id
        return DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name=self._device_name,
            manufacturer="Fronius",
            serial_number=self._serial_number,
            configuration_url=self.base_url,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll both inverter endpoints and return normalised state."""
        if self._request_lock.locked():
            _LOGGER.debug("Skipping update — previous request still in progress")
            if self.data:
                return self.data
            raise UpdateFailed("Previous request still in progress")

        async with self._request_lock:
            await self._fetch_version_info()
            powerunit = await self._digest_request("GET", API_POWERUNIT)
            power_limits = await self._digest_request("GET", API_POWER_LIMITS)

        try:
            mppt = powerunit["mppt"]
            pv_enabled = (
                int(mppt["mppt1"]["PV_MODE_MPP_01_U16"]) == 1
                and int(mppt["mppt2"]["PV_MODE_MPP_02_U16"]) == 1
            )
        except (KeyError, TypeError, ValueError) as err:
            raise UpdateFailed(f"Unexpected powerunit response: {err}") from err

        try:
            soft_limit = power_limits["exportLimits"]["activePower"]["softLimit"]
            export_enabled = bool(soft_limit["enabled"])
            export_power_limit = float(soft_limit["powerLimit"])
        except (KeyError, TypeError, ValueError) as err:
            raise UpdateFailed(f"Unexpected powerLimits response: {err}") from err

        if export_enabled:
            if self.config_entry.data.get(CONF_LAST_EXPORT_LIMIT) != export_power_limit:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, CONF_LAST_EXPORT_LIMIT: export_power_limit},
                )

        return {
            DATA_PV_ENABLED: pv_enabled,
            DATA_EXPORT_ENABLED: export_enabled,
            DATA_EXPORT_POWER_LIMIT: export_power_limit,
            DATA_SW_VERSION: self._sw_version,
            DATA_LAST_UPDATE: datetime.now(tz=timezone.utc),
        }

    async def async_set_pv_enabled(self, enabled: bool) -> None:
        """Toggle PV mode on both MPPT channels and refresh state."""
        value = 1 if enabled else 0
        payload: dict[str, Any] = {
            "mppt": {
                "mppt1": {"PV_MODE_MPP_01_U16": value},
                "mppt2": {"PV_MODE_MPP_02_U16": value},
            }
        }
        try:
            async with self._request_lock:
                await self._digest_request("POST", API_POWERUNIT, payload)
        except (UpdateFailed, TimeoutError, aiohttp.ClientError) as err:
            raise HomeAssistantError(f"Failed to set PV mode: {err}") from err
        if self.data is not None:
            self.async_set_updated_data({**self.data, DATA_PV_ENABLED: enabled})

    async def async_set_export_enabled(self, enabled: bool) -> None:
        """Toggle export limitation and refresh state."""
        if enabled:
            current_limit: float = float(
                self.config_entry.data.get(
                    CONF_LAST_EXPORT_LIMIT,
                    (self.data or {}).get(DATA_EXPORT_POWER_LIMIT, 0),
                )
            )
            payload: dict[str, Any] = {
                "exportLimits": {
                    "activePower": {
                        "hardLimit": {"powerLimit": 0},
                        "softLimit": {"enabled": True, "powerLimit": current_limit},
                        "activated": True,
                        "networkMode": "limitLocal",
                    },
                    "failSafeModeEnabled": True,
                    "autodetectedControlledDevices": {},
                    "staticControlledDevices": {},
                },
                "visualization": {
                    "wattPeakReferenceValue": current_limit,
                    "exportLimits": {"activePower": {}},
                },
            }
        else:
            payload = {
                "exportLimits": {
                    "activePower": {
                        "hardLimit": {"powerLimit": 0},
                        "softLimit": {"enabled": False, "powerLimit": 0},
                        "activated": False,
                        "networkMode": "limitLocal",
                    },
                    "failSafeModeEnabled": False,
                    "autodetectedControlledDevices": {},
                    "staticControlledDevices": {},
                },
                "visualization": {
                    "wattPeakReferenceValue": 0,
                    "exportLimits": {"activePower": {}},
                },
            }
        try:
            async with self._request_lock:
                await self._digest_request("POST", API_POWER_LIMITS, payload)
        except (UpdateFailed, TimeoutError, aiohttp.ClientError) as err:
            raise HomeAssistantError(f"Failed to set export limitation: {err}") from err
        if self.data is not None:
            updated = {**self.data, DATA_EXPORT_ENABLED: enabled}
            if enabled:
                updated[DATA_EXPORT_POWER_LIMIT] = current_limit
            self.async_set_updated_data(updated)
        if enabled:
            await asyncio.sleep(1)
            await self.async_request_refresh()

    async def async_set_export_power_limit(self, value: float) -> None:
        """Set the export soft-limit power value and refresh state."""
        export_enabled = bool(
            (self.data or {}).get(DATA_EXPORT_ENABLED, False)
        )
        payload: dict[str, Any] = {
            "exportLimits": {
                "activePower": {
                    "hardLimit": {"powerLimit": 0},
                    "softLimit": {"enabled": export_enabled, "powerLimit": value},
                    "activated": export_enabled,
                    "networkMode": "limitLocal",
                },
                "failSafeModeEnabled": export_enabled,
                "autodetectedControlledDevices": {},
                "staticControlledDevices": {},
            },
            "visualization": {
                "wattPeakReferenceValue": value,
                "exportLimits": {"activePower": {}},
            },
        }
        try:
            async with self._request_lock:
                await self._digest_request("POST", API_POWER_LIMITS, payload)
        except (UpdateFailed, TimeoutError, aiohttp.ClientError) as err:
            raise HomeAssistantError(f"Failed to set export power limit: {err}") from err
        if self.data is not None:
            self.async_set_updated_data({**self.data, DATA_EXPORT_POWER_LIMIT: value})
        if export_enabled:
            await asyncio.sleep(1)
            await self.async_request_refresh()

    async def _async_setup(self) -> None:
        """Fetch initial device metadata from the version endpoint."""
        try:
            await self._fetch_version_info()
        except UpdateFailed as err:
            _LOGGER.warning("Could not fetch version info during setup: %s", err)

    async def _fetch_version_info(self) -> None:
        """Fetch and cache device name, serial number, and GEN24 software version."""
        data = await self._plain_get(API_VERSION)
        self._device_name = str(data.get("devicename") or "Fronius Gen24")
        serial = data.get("serialNumber")
        self._serial_number = str(serial) if serial else None
        sw_revisions = data.get("swrevisions") or {}
        self._sw_version = sw_revisions.get("GEN24")

    async def _plain_get(self, uri: str) -> dict[str, Any]:
        """Make an unauthenticated GET request and return the parsed JSON body."""
        url = f"{self.base_url}{uri}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await self.session.get(url)
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except aiohttp.ClientResponseError as err:
            raise UpdateFailed(f"GET {uri} returned HTTP {err.status}") from err
        except (TimeoutError, aiohttp.ClientError) as err:
            raise UpdateFailed(f"GET {uri} failed: {err}") from err

    async def _digest_request(
        self,
        method: str,
        uri: str,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a digest-authenticated request to the inverter.

        Performs the two-step digest auth handshake: HEAD to obtain the
        challenge, then the real request with the computed Authorization header.
        """
        url = f"{self.base_url}{uri}"

        # Step 1: HEAD request to obtain the WWW-Authenticate challenge.
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                challenge_resp = await self.session.head(url)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise UpdateFailed(f"Auth challenge failed for {uri}: {err}") from err

        challenge_header = challenge_resp.headers.get(
            "x-www-authenticate"
        ) or challenge_resp.headers.get("www-authenticate")
        if not challenge_header:
            raise UpdateFailed(
                f"No auth challenge header returned from {url}. "
                "Check that the host and credentials are correct."
            )

        params = _parse_digest_challenge(challenge_header)
        auth_value = _compute_digest_auth(method, uri, self.username, self.password, params)
        headers = {
            "Authorization": auth_value,
            "Content-Type": "application/json",
        }

        # Step 2: Actual request with the computed Authorization header.
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                if method.upper() == "GET":
                    resp = await self.session.get(url, headers=headers)
                else:
                    resp = await self.session.post(url, headers=headers, json=json_data)
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except aiohttp.ClientResponseError as err:
            raise UpdateFailed(
                f"{method} {uri} returned HTTP {err.status}"
            ) from err
        except (TimeoutError, aiohttp.ClientError) as err:
            raise UpdateFailed(f"{method} {uri} failed: {err}") from err
