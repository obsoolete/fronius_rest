"""Config flow for the Fronius Gen24 REST integration."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    API_POWERUNIT,
    API_VERSION,
    CONF_RESOLVED_IP,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    REQUEST_TIMEOUT,
)
from .coordinator import (
    CONF_HOST,
    _async_resolve_host,
    _compute_digest_auth,
    _is_ip_address,
    _normalize_base_url,
    _parse_digest_challenge,
)


async def _validate_connection(
    hass: HomeAssistant,
    host: str,
    username: str,
    password: str,
) -> dict[str, str | None]:
    """Validate connectivity and credentials against the inverter.

    Returns a dict with ``device_name`` and ``serial`` on success.
    Raises CannotConnect or InvalidAuth on failure.
    """
    try:
        configured_url = _normalize_base_url(host)
        resolved_ip = await _async_resolve_host(configured_url)
    except (TimeoutError, OSError, ValueError) as err:
        raise CannotConnect from err

    base_url = str(configured_url.with_host(resolved_ip)).rstrip("/")
    request_headers = (
        {}
        if _is_ip_address(configured_url.host or "")
        else {"Host": configured_url.raw_authority}
    )

    session = async_get_clientsession(hass)

    # Step 1: Plain GET to /api/status/version — validates the host is reachable
    # and extracts device name and serial number for the HA device registry.
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            version_resp = await session.get(
                f"{base_url}{API_VERSION}", headers=request_headers
            )
            version_resp.raise_for_status()
            version_data = await version_resp.json(content_type=None)
    except (TimeoutError, aiohttp.ClientError) as err:
        raise CannotConnect from err

    device_name: str = str(version_data.get("devicename") or "Fronius Gen24")
    serial = version_data.get("serialNumber")
    serial_str: str | None = str(serial) if serial else None

    # Step 2: Digest auth check to verify the credentials are accepted.
    url = f"{base_url}{API_POWERUNIT}"
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            challenge_resp = await session.head(url, headers=request_headers)
    except (TimeoutError, aiohttp.ClientError) as err:
        raise CannotConnect from err

    challenge_header = challenge_resp.headers.get(
        "x-www-authenticate"
    ) or challenge_resp.headers.get("www-authenticate")
    if not challenge_header:
        raise CannotConnect

    params = _parse_digest_challenge(challenge_header)
    auth_value = _compute_digest_auth("GET", API_POWERUNIT, username, password, params)
    headers = {
        **request_headers,
        "Authorization": auth_value,
        "Content-Type": "application/json",
    }

    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            resp = await session.get(url, headers=headers)
    except (TimeoutError, aiohttp.ClientError) as err:
        raise CannotConnect from err

    if resp.status in (401, 403):
        raise InvalidAuth
    if not resp.ok:
        raise CannotConnect

    return {
        "device_name": device_name,
        "serial": serial_str,
        "resolved_ip": resolved_ip,
    }


class FroniusRestConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fronius Gen24."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> FroniusRestOptionsFlow:
        """Return the options flow for this handler."""
        return FroniusRestOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].rstrip("/")
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            try:
                info = await _validate_connection(self.hass, host, username, password)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                normalized_host = str(_normalize_base_url(host)).rstrip("/")
                unique_id = info["serial"] or normalized_host
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["device_name"],
                    data={
                        CONF_HOST: normalized_host,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                        **(
                            {CONF_RESOLVED_IP: info["resolved_ip"]}
                            if not _is_ip_address(
                                _normalize_base_url(normalized_host).host or ""
                            )
                            else {}
                        ),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_USERNAME): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": "technician", "label": "Technician"},
                                {"value": "customer", "label": "Customer"},
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=1,
                            unit_of_measurement="seconds",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure the inverter connection."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].rstrip("/")
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            try:
                info = await _validate_connection(
                    self.hass, host, username, password
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                normalized_host = str(_normalize_base_url(host)).rstrip("/")
                if info["serial"] is not None:
                    await self.async_set_unique_id(info["serial"])
                    self._abort_if_unique_id_mismatch()

                data = {
                    **entry.data,
                    CONF_HOST: normalized_host,
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                }
                configured_host = _normalize_base_url(normalized_host).host or ""
                if _is_ip_address(configured_host):
                    data.pop(CONF_RESOLVED_IP, None)
                else:
                    data[CONF_RESOLVED_IP] = info["resolved_ip"]

                return self.async_update_reload_and_abort(
                    entry,
                    title=info["device_name"] or entry.title,
                    data=data,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST, default=entry.data[CONF_HOST]
                    ): str,
                    vol.Required(
                        CONF_USERNAME, default=entry.data[CONF_USERNAME]
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": "technician", "label": "Technician"},
                                {"value": "customer", "label": "Customer"},
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_PASSWORD, default=entry.data[CONF_PASSWORD]
                    ): str,
                }
            ),
            errors=errors,
        )


class FroniusRestOptionsFlow(OptionsFlow):
    """Handle options for Fronius Gen24."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=int(current_interval)
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=1,
                            unit_of_measurement="seconds",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )


class CannotConnect(Exception):
    """Error raised when the inverter cannot be reached."""


class InvalidAuth(Exception):
    """Error raised when credentials are rejected."""
