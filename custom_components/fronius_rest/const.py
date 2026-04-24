"""Constants for the Fronius Gen24 REST integration."""

DOMAIN = "fronius_rest"

CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 120

REQUEST_TIMEOUT = 10

# Coordinator data keys
DATA_PV_ENABLED = "pv_enabled"
DATA_EXPORT_ENABLED = "export_enabled"
DATA_EXPORT_POWER_LIMIT = "export_power_limit"
DATA_SW_VERSION = "sw_version"
DATA_LAST_UPDATE = "last_update"

CONF_LAST_EXPORT_LIMIT = "last_export_limit"

# API endpoints
API_POWERUNIT = "/api/config/powerunit"
API_POWER_LIMITS = "/api/config/limit_settings/powerLimits"
API_VERSION = "/api/status/version"
