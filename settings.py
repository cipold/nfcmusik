SERVER_HOST_MASK = "0.0.0.0"
MUSIC_ROOT = "/home/pi/Music"
DEFAULT_VOLUME = 70

# shut down wlan0 interface N seconds after startup (or last server interaction)
WLAN_OFF_DELAY = 180

# control bytes for NFC payload
CONTROL_BYTES = dict(
    MUSIC_FILE=b'\x11',
)
