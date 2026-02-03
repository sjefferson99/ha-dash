## Logging
# Level 0-4: 0 = Disabled, 1 = Critical, 2 = Error, 3 = Warning, 4 = Info
LOG_LEVEL = 2
# Handlers: Populate list with zero or more of the following log output handlers (case sensitive): "Console", "File"
LOG_HANDLERS = ["Console", "File"]
# Max log file size in bytes, there will be a maximum of 2 files at this size created
LOG_FILE_MAX_SIZE = 10240

## WIFI
WIFI_SSID = ""
WIFI_PASSWORD = ""
WIFI_COUNTRY = "GB"
WIFI_CONNECT_TIMEOUT_SECONDS = 10
WIFI_CONNECT_RETRIES = 1
WIFI_RETRY_BACKOFF_SECONDS = 5
# Leave as none for MAC based unique hostname or specify a custom hostname string
CUSTOM_HOSTNAME = None

## Freqyuency of NTP sync in seconds (minimum 60 seconds)
NTP_SYNC_INTERVAL_SECONDS = 600

## Button Configuration
BUTTON1_PIN = 15
LED1_PIN = 14

## Home Assistant Configuration
HA_HOST = "192.168.1.100"  # Your Home Assistant IP address
HA_PORT = "8123"
HA_TOKEN = "your_long_lived_access_token_here"  # Create in HA Profile -> Security -> Long-Lived Access Tokens
BUTTON1_ENTITY = "light.living_room"  # Replace with your actual entity_id
LED1_ENTITY = "light.living_room"  # Replace with your actual entity_id

## Overclocking - Pico1 default 133MHz, Pico2 default 150MHz
CLOCK_FREQUENCY = 133000000
