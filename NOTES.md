# 12.48" Waveshare e-Paper (B) + ESP32

## Hardware

- **Display**: 12.48inch e-Paper Module (B) — 1304x984px, tri-color (black/red/white)
- **Board**: Waveshare e-Paper ESP32 Driver Board (dev kit with acrylic frame)
- **ESP32 module**: ESP32-D0WD-V3 (rev v3.1), dual core 240MHz, 4MB flash, **no PSRAM** (WROOM-class)
- **Heap**: 376KB total, 351KB free, **114KB max contiguous alloc** (fragmentation)
- **HW version**: V1 (or at least, no V2 marking found)
- **Serial port**: `/dev/cu.SLAB_USBtoUART`
- **MAC**: b0:cb:d8:cd:04:68
- **State when found**: Boot-looping (no valid firmware)

The display is internally 4 sub-panels (M1/S1 top, M2/S2 bottom), each with its
own chip select and busy pin. 16 GPIO pins total, all pre-wired on the driver board.

## Repo & Library

- **Repo**: https://github.com/waveshareteam/12.48inch-e-paper
- **Cloned to**: `waveshare-repo/`
- **ESP32 library**: `waveshare-repo/esp32/esp32-epd-12in48/` — Arduino framework, software SPI (bit-banged)
- **Three platform versions**: RPi (C + Python), Arduino UNO (with external SRAM), ESP32

## Platform Comparison

| | RPi | Arduino UNO | ESP32 |
|---|---|---|---|
| RAM strategy | Full framebuffer (~320KB, trivial) | External SRAM chips (3x 23LC1024) | Half-height buffer (1304x492, ~80KB) |
| SPI | Hardware via spidev (PR #7) or bit-bang (stock) | Hardware `SPI.transfer()` | Bit-banged `DEV_SPI_WriteByte()` |
| Draw passes | 1 (full screen) | 1 (full screen via SRAM) | 4 (top/bottom × black/red) |
| Partial refresh | No | No | No |
| BMP loading | Yes (`GUI_ReadBmp`) | No | No |

**No partial refresh on any platform** — hardware limitation of tri-color e-ink.

## Known Issues

### ESP32 ReadBusy hang (issue #3)
Multiple users report `EPD_12in48_M1_ReadBusy` never returning. The busy-wait
loop has no timeout. Could be V1/V2 mismatch, wiring, or a genuine driver bug.
Never resolved upstream. **We should add a timeout to busy loops.**

### ESP32 crash (issue #2)
Caused by having both Arduino UNO and ESP32 boards connected simultaneously.
Resolved by only using the ESP32 board.

### Red channel inversion (PR #7 comments)
The RPi Python optimized version had inverted red. Fix: bitwise NOT on red channel
bytes. May or may not apply to ESP32 code.

## PRs & Community Work

### PR #7 — SPI performance (RPi Python only)
MediumFidelity replaced bit-banged C SPI with Python `spidev` + bulk transfers.
**2m41s → 35s** on Pi Zero W. The concept applies to ESP32 too — switching from
`DEV_SPI_WriteByte()` to hardware SPI bulk transfers would speed up data
transmission significantly. Not critical for e-ink (refresh is the bottleneck)
but worth doing.

### Other PRs
- #9, #10: Trivial Python code shortening
- #6: STM32 API fix
- #11, #13, #14: Merged by Waveshare — V2 support, BCM2835 compat, 32/64-bit compat

## Alternative: cale-idf (martinberlin)

https://github.com/martinberlin/cale-idf — 349 stars, actively maintained (last
commit June 2025). ESP-IDF component, NOT Arduino.

### What it offers
- **Hardware SPI with DMA** (not bit-banged) — ~794ms to send buffer vs minutes
- **Full Adafruit GFX API** — drawLine, fillRect, print/println, setFont, setRotation, etc.
- **Rich font support** — FreeFont family, Ubuntu fonts up to 120pt, TTF converter
- **Unified canvas** — abstracts 4-panel split, you just draw on 1304x984
- **Tri-color class**: `Wave12I48RB` (file: `wave12i48BR.cpp`)
- Performance: **~5.5s total** (794ms data transfer + 4.7s e-ink refresh)

### Docs & links
- B/W wiki (includes PSRAM pin hack): https://github.com/martinberlin/cale-idf/wiki/wave12i48-1304x984-EOL
- Tri-color wiki: https://github.com/martinberlin/cale-idf/wiki/color-wave12i48BR-1304x984-B%7CR
- CalEPD component repo: https://github.com/martinberlin/CalEPD
- PlatformIO build: https://github.com/martinberlin/cale-platformio
- Good Display datasheet (IL0326): http://www.e-paper-display.com/products_detail/productId=414.html

### Why we can't use it (without hardware changes)
1. **Requires PSRAM** — allocates full framebuffer (~160KB B/W, ~320KB tri-color)
   via `heap_caps_malloc(size, MALLOC_CAP_SPIRAM)`. Needs ESP32-WROVER, not WROOM.
2. **GPIO 16/17 conflict** — WROVER uses these for PSRAM SPI. Waveshare board uses
   GPIO 16 (M2_CS) and 17 (M2S2_DC). Wiki documents a physical pin-bending hack
   to remap to GPIO 21/27.
3. **ESP-IDF only** — no Arduino framework support. Can build via PlatformIO with
   `framework = espidf`.
4. **Still no partial refresh** — same hardware limitation.

### If we ever swap to WROVER
- Build via PlatformIO + ESP-IDF or native `idf.py`
- GPIO config via Kconfig menuconfig or `-D` build flags
- Config examples in `config-examples/sdkconfig_Wave12I48_PSRAM_active`
- The `cale-platformio` sister repo provides PlatformIO skeleton

## Tooling

- **Build**: PlatformIO (`brew install platformio`)
- **Framework**: Arduino (via `framework-arduinoespressif32`)
- **Board**: `esp32dev`
- **Project initialized**: `platformio.ini` in project root

## Timing

Measured 2026-03-11 with status board sketch:

| Phase | Bit-bang | HW SPI 4MHz | HW SPI 10MHz | + Bulk sends |
|---|---|---|---|---|
| Init | 411 ms | 409 ms | 408 ms | 408 ms |
| Clear | 15,056 ms | 13,233 ms | 12,774 ms | 12,173 ms |
| Data transfer (4 passes) | 3,201 ms | 1,403 ms | 944 ms | 344 ms |
| E-ink refresh | 11,901 ms | 11,900 ms | 11,900 ms | 11,900 ms |
| **Total** | **~33 s** | **~27 s** | **~26.5 s** | **~25.3 s** |

CalEPD on WROVER reports ~5.5s total (794ms transfer + 4.7s refresh).

## SPI Notes

- **Must use HSPI**, not VSPI. VSPI default pins (18/19/23/5) conflict with display
  GPIOs (M2_BUSY/S2_CS/M1_CS/M2S2_RST). Even when remapping, VSPI may claim defaults.
- Waveshare board: SCK=GPIO13, MOSI=GPIO14 (happen to be HSPI-native pins).
- All three implementations (ours, Arduino Waveshare, CalEPD) use SPI Mode 0, MSBFIRST.
- Arduino Waveshare and CalEPD both use 4MHz. We pushed to 10MHz with no issues.

## Architecture

### System overview
```
Docker container (OMV) → MQTT broker (existing, Home Assistant) → ESP32 → e-ink display
```

### ESP32 firmware (next steps)
- WiFi connection
- MQTT subscriber (PubSubClient library)
- JSON parsing → render with Adafruit GFX templates
- OTA updates (ArduinoOTA) so we don't need the USB cable after initial setup

### Docker container (OMV home server)
- Reads data sources, formats JSON, publishes to MQTT topic
- Decides what to show and when (schedule or event-driven)
- LLM integration for wildcard mode

### Data sources
- **Logseq** — daily journal, focus, events, notes/todos, forgotten `#later` items
  - Synced via **Syncthing** from laptop and Android phone directly to OMV
  - Docker container reads markdown files as a mounted volume
  - No Logseq Sync service needed — Syncthing handles all devices
  - Note: Logseq DB version coming, may change storage format
- **Upcoming dates** — birthdays, anniversaries. Flag ~7 days out, especially if no action taken yet
- **Precipitation forecast** — Meteo Blue API (paid access, hourly). "When will it rain?" for dog walk planning
- **LLM-generated content** — poems based on daily context, wildcard information surfacing
- **Quotes** — fallback filler when the day is light

### Display modes
1. **Structured** — predefined fields (title, items, events, weather, footer). Container populates known JSON shape
2. **Wildcard** — LLM decides what information to show. Can suggest new layouts or reuse structured templates as examples

### Refresh cadence
- Probably once an hour or once a day
- USB powered for now (dev board), battery is a future consideration
- Deep sleep between refreshes if we move to battery later

## Completed

- [x] Flash stock demo and check for ReadBusy hang — WORKS, no hang
- [x] Add timeout to busy loops (60s)
- [x] Write a simple message display sketch
- [x] Switch DEV_SPI_WriteByte to hardware SPI.transfer() — HSPI 10MHz, 3.2s → 0.9s
- [x] Bulk SPI sends (scanline batching) — 0.9s → 0.34s
- [x] Adafruit GFX with EinkCanvas half-height abstraction (cross-boundary drawing)
- [x] Memory check: max alloc 114KB, can't fit full 160KB buffer. Half-height confirmed necessary
- [x] Deghost routine: 15 cycles black/red/white

## TODO

- [x] WiFi + MQTT listener on ESP32
- [x] JSON parsing → template rendering
- [x] OTA update support (ArduinoOTA, blocked by VLAN)
- [x] Docker container scaffold
- [x] Meteo Blue API integration (3-day forecast, rain/snow split, walk windows)
- [x] Upcoming dates source (YAML with recurring/one-time dates)
- [ ] Logseq markdown parser (read journals, extract todos)
- [ ] Template system with multiple layouts
- [ ] Wildcard/LLM mode
- [ ] Consider WROVER upgrade path for CalEPD
- [ ] Migrate weather "daily condition" from Open-Meteo to Météo-France direct (see below)
- [ ] Evaluate ESPHome + IT8951 driver as a SensCraft alternative (see below)
- [ ] If ESPHome path wins: remove SensCraft publish, env vars, and `senscraft.py`
- [ ] File issue / PR upstream on `koosoli/Seeed-10.3-inch-IT8951-ESPHome-Drivers`: text antialiasing only works when an explicit background colour is passed to `it.print(...)`. Without it, ESPHome's bpp:4 font renderer blends against an assumed-black backdrop, which produces smooth white-on-dark text but flattens black-on-light text to hard 1-bit. Workaround in our YAML is to pass the background colour to every `it.print` call. Driver could either default to assuming WHITE bg, or document the requirement. See test grid in commit history.
- [ ] Consider switching from lambda-based `display:` to LVGL (`lvgl:`) for layout — gives proper grid containers (`LV_GRID_CONTENT` for content-sized rows, `LV_GRID_FR` for fractional space), declarative vertical/horizontal alignment, and reflow when text wraps. Trade-offs: it's a full rewrite of the display config, ~150–300KB more firmware, and LVGL renders text through its own font engine which bypasses ESPHome's `display::print` — so we'd need to re-verify that the explicit-background-colour antialiasing trick still applies (likely doesn't; LVGL has its own anti-aliasing config). Defer until lambda + manual measuring becomes the bottleneck.

## Future: weather provider — Météo-France direct

Currently using Open-Meteo's `/v1/meteofrance` endpoint with `meteofrance_arome_france_hd` + `meteofrance_arpege_europe`. Underlying model data is Météo-France's, but the **daily aggregation** is Open-Meteo's: it picks the most-significant hourly weather code, which produces "Light rain" for a day with 23h overcast and 1h trace drizzle.

Workaround in place: derive the dominant hourly weather code ourselves during waking hours.

Why Météo-France direct may still be worth it later:
- Their daily summary is human-tuned / climatology-aware
- Fewer pessimistic mismatches between condition and precipitation
- We're already targeting their data — going through one fewer hop

Costs to plan for:
- Register on portail-api.meteofrance.fr (token-based auth, French portal)
- Different condition codes — own pictocodes, not WMO. Need a new icon mapping table.
- Endpoint paths and JSON shape to learn
- Still need Open-Meteo for the hourly walk-window logic, OR refactor to use Météo-France for hourly too
- Two providers running side-by-side during transition (treat the new one as `weather_alt` first, compare for a week, then promote)

## Future: ESPHome on the reTerminal E1003

Alternative to the SensCraft HMI cloud path. Same hardware, different software stack.

Reference: [XDA article — touch-enabled e-paper Home Assistant dashboard](https://www.xda-developers.com/built-touch-enabled-epaper-home-assistant-dashboard-better-any-tablet/) and [Adam-Home-Assistant-Snippets ESPHome configs](https://github.com/Incipiens/Adam-Home-Assistant-Snippets/tree/main/ESPHome/reTerminal%20E1003%20-%20Touch%20controls).

Stack:
- **Display driver**: [koosoli/Seeed-10.3-inch-IT8951-ESPHome-Drivers](https://github.com/koosoli/Seeed-10.3-inch-IT8951-ESPHome-Drivers) — custom ESPHome external component for the IT8951 e-paper controller. New (0 stars at time of writing) but actively maintained by the same author who built ESPHomeDesigner.
- **Touch**: stock ESPHome [GT911 platform](https://esphome.io/components/touchscreen/gt911) — works out of the box, independent of the display driver. Touch areas are pixel rectangles that fire HA actions.
- **Layout editor**: [koosoli/ESPHomeDesigner](https://github.com/koosoli/ESPHomeDesigner) (845 stars). Drag-and-drop canvas → generates ESPHome lambda or LVGL YAML. Distributed via HACS. Round-trip imports existing YAML back to canvas. 55+ widget modules. Specifically targets e-paper hardware.

Pros vs SensCraft:
- Fully local, no cloud dependency
- Native HA integration (no MQTT-to-HTTP bridge)
- Touch controls that talk directly to HA
- Open source end-to-end

Trade-offs:
- IT8951 driver lacks **partial refresh** (open issue #1). The XDA article reports ~15s full refresh, but that's the driver's current waveform choice (likely GC16 + clear cycles), **not a hardware limit**. The IT8951 hardware supports multiple waveforms: GC16 ~450–700ms (full grayscale), DU ~250–300ms (1-bit fast text), A2 ~120ms (animation). With waveform selection a full redraw can be sub-second, which makes touch responses feel near-instant and `mode: restart` debounce less critical. Worth checking what mode the driver uses by default and whether it can be picked per-update.
- Layout has the **same fundamental problem as SensCraft**: absolute pixel positioning, no flow layout. ESPHomeDesigner's `print_wrapped_text` helper does runtime word-wrap inside a single text box, but content below doesn't reflow when text overflows. Have to leave worst-case gaps between widgets manually. LVGL output supports grid layout (`NxM`) but not flex.
- LLM narrative + Open-Meteo logic would need to move from our Python server into either ESPHome's HTTP fetch + lambda parsing, or stay in Python and publish into HA as sensor entities that the device reads via the HA API integration. The latter is cleaner.

Migration order if we ever do it:
1. Port the daily payload into HA sensor entities (one per field — date, weather.today.body, walk, upcoming.0.text, etc.)
2. Flash ESPHome on the device with the IT8951 driver
3. Build initial layout in ESPHomeDesigner pulling from those sensors
4. Add touch interactions later

## Future: 13.3" Spectra 6 full-colour e-ink

7 colours (black, white, red, yellow, blue, green, orange), 1600x1200. Slower refresh (~30s+) but much richer output for a daily status board.

- Pimoroni Inky Impression 13.3": https://shop.pimoroni.com/products/inky-impression?variant=55186435277179
- Waveshare 13.3" e-Paper HAT+: https://www.waveshare.com/13.3inch-e-paper-hat-plus-e.htm
