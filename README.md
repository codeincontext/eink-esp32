# eink-esp32

A daily status board on a large tri-color e-ink display, driven by MQTT.

**Hardware:** ESP32 (WROOM) + Waveshare 12.48" e-Paper Module (B) — 1304x984, black/white/red.

**Architecture:** A Python server assembles data from various sources, publishes a JSON payload via MQTT, and the ESP32 subscribes and renders it to the display.

```
[ Python server ] → MQTT → [ ESP32 ] → [ e-ink display ]
     (Docker)                              (1304x984, tri-color)
```

## What's on the display

- **Upcoming dates** — birthdays, anniversaries, events from a YAML file. Items within 2 days are highlighted in red.
- **Weather** — 3-day forecast from [Meteoblue](https://www.meteoblue.com/) with rain/snow split, precipitation in red ink. Includes a dog walk window finder (best dry hours between 8:00–18:00).
- **Thought of the day** — a rotating quote with author and context paragraph, anchored to the bottom of the display.

## ESP32 firmware

Built with PlatformIO and Adafruit GFX. The display is rendered in four passes (black top, black bottom, red top, red bottom) using a half-height canvas to fit in the ESP32's limited RAM. SPI runs on HSPI at 10MHz.

```
cp src/config.example.h src/config.h  # edit with your WiFi/MQTT credentials
pio run -t upload
```

## Server

A Python service that polls data sources and publishes to MQTT. Runs in Docker.

```
cd server
cp .env.example .env                  # edit with your MQTT/API credentials
cp data/dates.example.yml data/dates.yml  # add your own dates
docker compose up -d
```

### Data sources

| Source | File / Config | Notes |
|--------|--------------|-------|
| Dates | `data/dates.yml` | Recurring (DD-MM) or one-time (YYYY-MM-DD) |
| Holidays | Computed + optional `data/holidays.ics` | Easter-relative dates, ICS import |
| Weather | Meteoblue API key in `.env` | 3-day forecast, rain/snow, walk windows |
| Thoughts | `data/thoughts.yml` | Quote + author + context, daily rotation |

### Red ink convention

The server uses a `\x01` byte as a marker in strings. The firmware renders text before the marker in black and text after in red. This is used for urgent dates, precipitation amounts, and tight walk windows.

## Hardware notes

- VSPI pins conflict with display GPIOs — must use HSPI
- No partial refresh on tri-color e-ink — full refresh takes ~12s
- Display panels are wired as two pairs (M2/S2 top, M1/S1 bottom) with separate DC/RST lines
