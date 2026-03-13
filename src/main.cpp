#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <ArduinoOTA.h>

#include "DEV_Config.h"
#include "utility/EPD_12in48b.h"
#include "EinkCanvas.h"
#include "config.h"

int Version = 1;

#include <Fonts/FreeSansBold24pt7b.h>
#include <Fonts/FreeSansBold18pt7b.h>
#include <Fonts/FreeSans18pt7b.h>
#include <Fonts/FreeSans12pt7b.h>
#include <Fonts/FreeSerifBoldItalic24pt7b.h>
#include <Fonts/FreeSerifItalic18pt7b.h>
#include <Fonts/FreeSans9pt7b.h>

#define BLACK 0
#define WHITE 1

#define MAX_SECTIONS 4
#define MAX_ITEMS    6
#define MAX_STR      128

// ── Display data (populated from MQTT JSON) ──

struct Section {
    char heading[64];
    char items[MAX_ITEMS][MAX_STR];
    int  itemCount;
};

static char    dTitle[64];
static char    dSubtitle[MAX_STR];
static Section dSections[MAX_SECTIONS];
static int     dSectionCount;
static char    dThoughtText[256];
static char    dThoughtAuthor[64];
static char    dThoughtContext[512];

#define MAX_WEATHER_DAYS 3
struct WeatherDay {
    char label[16];
    int  high;
    int  low;
    char condition[24];
    float rainMm;
    float snowCm;
    int   precipProb;
};
static WeatherDay dWeather[MAX_WEATHER_DAYS];
static int        dWeatherCount;
static char       dWalk[MAX_STR];

static char    dFooter[MAX_STR];

// ── Globals ──

static EinkCanvas   canvas;
static WiFiClient   wifiClient;
static PubSubClient mqtt(wifiClient);
static bool         needsRefresh    = false;
static unsigned long lastMqttAttempt = 0;

// ── WiFi ──

static void connectWiFi()
{
    printf("WiFi: connecting to %s", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 60) {
        delay(500);
        printf(".");
        attempts++;
    }
    printf("\r\n");

    if (WiFi.status() == WL_CONNECTED)
        printf("WiFi: connected, IP=%s\r\n", WiFi.localIP().toString().c_str());
    else
        printf("WiFi: FAILED after %d attempts\r\n", attempts);
}

// ── MQTT ──

static void onMqttMessage(char *topic, byte *payload, unsigned int length)
{
    printf("[%6lu] MQTT: %u bytes on %s\r\n", millis(), length, topic);

    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, (const char *)payload, length);
    if (err) {
        printf("JSON error: %s\r\n", err.c_str());
        return;
    }

    strlcpy(dTitle,    doc["title"]    | "", sizeof(dTitle));
    strlcpy(dSubtitle, doc["subtitle"] | "", sizeof(dSubtitle));
    strlcpy(dFooter,   doc["footer"]   | "", sizeof(dFooter));

    JsonObject thought = doc["thought"];
    if (!thought.isNull()) {
        strlcpy(dThoughtText,    thought["text"]    | "", sizeof(dThoughtText));
        strlcpy(dThoughtAuthor,  thought["author"]  | "", sizeof(dThoughtAuthor));
        strlcpy(dThoughtContext, thought["context"] | "", sizeof(dThoughtContext));
    } else {
        dThoughtText[0]    = '\0';
        dThoughtAuthor[0]  = '\0';
        dThoughtContext[0] = '\0';
    }

    JsonArray sections = doc["sections"];
    dSectionCount = 0;
    for (JsonObject s : sections) {
        if (dSectionCount >= MAX_SECTIONS) break;
        Section &sec = dSections[dSectionCount];
        strlcpy(sec.heading, s["heading"] | "", sizeof(sec.heading));
        sec.itemCount = 0;
        JsonArray items = s["items"];
        for (JsonVariant item : items) {
            if (sec.itemCount >= MAX_ITEMS) break;
            const char *str = item.as<const char *>();
            strlcpy(sec.items[sec.itemCount], str ? str : "", MAX_STR);
            sec.itemCount++;
        }
        dSectionCount++;
    }

    JsonObject wx = doc["weather"];
    dWeatherCount = 0;
    if (!wx.isNull()) {
        JsonArray days = wx["days"];
        for (JsonObject d : days) {
            if (dWeatherCount >= MAX_WEATHER_DAYS) break;
            WeatherDay &wd = dWeather[dWeatherCount];
            strlcpy(wd.label, d["label"] | "", sizeof(wd.label));
            wd.high = d["high"] | 0;
            wd.low = d["low"] | 0;
            strlcpy(wd.condition, d["condition"] | "", sizeof(wd.condition));
            wd.rainMm = d["rain_mm"] | 0.0f;
            wd.snowCm = d["snow_cm"] | 0.0f;
            wd.precipProb = d["precip_prob"] | 0;
            dWeatherCount++;
        }
        strlcpy(dWalk, wx["walk"] | "", sizeof(dWalk));
    } else {
        dWalk[0] = '\0';
    }

    needsRefresh = true;
}

static void connectMQTT()
{
    String clientId = "eink-" + String((uint32_t)ESP.getEfuseMac(), HEX);
    printf("MQTT: connecting to %s:%d as %s...\r\n",
           MQTT_HOST, MQTT_PORT, clientId.c_str());

    bool ok;
    if (strlen(MQTT_USER) > 0)
        ok = mqtt.connect(clientId.c_str(), MQTT_USER, MQTT_PASSWORD);
    else
        ok = mqtt.connect(clientId.c_str());

    if (ok) {
        printf("MQTT: connected\r\n");
        mqtt.subscribe(MQTT_TOPIC);
        printf("MQTT: subscribed to %s\r\n", MQTT_TOPIC);
    } else {
        printf("MQTT: failed, rc=%d\r\n", mqtt.state());
    }
}

// ── Rendering ──
//
// Single function renders both channels. The `black` flag draws text and
// lines; the `red` flag draws accent marks. Y tracking is identical in
// both passes so positions stay in sync across the 4-pass send.

// Word-wrap text within a pixel width, advancing y. When draw=false,
// only tracks y so red/black passes stay in sync.
static int16_t drawWrapped(EinkCanvas &c, const char *text, int16_t x, int16_t y,
                           int16_t maxW, int16_t lineH, bool draw,
                           uint16_t *outMaxW = nullptr)
{
    char buf[512];
    strlcpy(buf, text, sizeof(buf));

    char *rest = buf;
    char *word;
    char line[256];
    line[0] = '\0';
    uint16_t widest = 0;

    while ((word = strtok_r(rest, " ", &rest)) != nullptr) {
        char candidate[256];
        if (line[0])
            snprintf(candidate, sizeof(candidate), "%s %s", line, word);
        else
            strlcpy(candidate, word, sizeof(candidate));

        int16_t bx, by;
        uint16_t tw, th;
        c.getTextBounds(candidate, 0, 0, &bx, &by, &tw, &th);

        if (tw > (uint16_t)maxW && line[0]) {
            int16_t lbx, lby; uint16_t lw, lh;
            c.getTextBounds(line, 0, 0, &lbx, &lby, &lw, &lh);
            if (lw > widest) widest = lw;
            if (draw) { c.setCursor(x, y); c.print(line); }
            y += lineH;
            strlcpy(line, word, sizeof(line));
        } else {
            strlcpy(line, candidate, sizeof(line));
        }
    }

    if (line[0]) {
        int16_t lbx, lby; uint16_t lw, lh;
        c.getTextBounds(line, 0, 0, &lbx, &lby, &lw, &lh);
        if (lw > widest) widest = lw;
        if (draw) { c.setCursor(x, y); c.print(line); }
        y += lineH;
    }

    if (outMaxW) *outMaxW = widest;
    return y;
}

// Render text with \x01 red marker. Text before marker: black pass.
// Text after marker: red pass. Cursor positioned naturally via invisible print.
static void drawMarked(EinkCanvas &c, int16_t x, int16_t y,
                        bool black, bool red, const char *text)
{
    const char *marker = strchr(text, '\x01');
    if (!marker) {
        if (black) { c.setCursor(x, y); c.print(text); }
        return;
    }

    char prefix[MAX_STR];
    int len = min((int)(marker - text), MAX_STR - 1);
    memcpy(prefix, text, len);
    prefix[len] = '\0';
    const char *suffix = marker + 1;

    if (black && prefix[0]) {
        c.setCursor(x, y);
        c.print(prefix);
    }

    if (red && suffix[0]) {
        c.setTextColor(WHITE);
        c.setCursor(x, y);
        c.print(prefix);
        c.setTextColor(BLACK);
        c.print(suffix);
    }
}

static void renderScene(EinkCanvas &c, bool black, bool red)
{
    c.setTextColor(BLACK);
    const int16_t L = 80;
    const int16_t W = 1144;
    int16_t y = 60;

    // Title
    c.setFont(&FreeSansBold24pt7b);
    if (dTitle[0]) {
        if (black) { c.setCursor(L, y); c.print(dTitle); }
        if (red) c.fillRect(L, y + 8, 200, 4, BLACK);
        y += 50;
    }

    // Subtitle
    c.setFont(&FreeSans18pt7b);
    if (dSubtitle[0]) {
        if (black) { c.setCursor(L, y); c.print(dSubtitle); }
        y += 16;
    }

    // Rule under title block
    if (black) c.drawFastHLine(L, y, W, BLACK);
    y += 50;

    // Sections
    for (int s = 0; s < dSectionCount; s++) {
        Section &sec = dSections[s];

        c.setFont(&FreeSansBold18pt7b);
        if (black) { c.setCursor(L, y); c.print(sec.heading); }
        if (red) c.fillCircle(L - 25, y - 8, 6, BLACK);
        y += 38;

        c.setFont(&FreeSans12pt7b);
        for (int i = 0; i < sec.itemCount; i++) {
            drawMarked(c, L + 20, y, black, red, sec.items[i]);
            y += 30;
        }
        y += 30;
    }

    // Weather
    if (dWeatherCount > 0) {
        c.setFont(&FreeSansBold18pt7b);
        if (black) { c.setCursor(L, y); c.print("Weather"); }
        if (red) c.fillCircle(L - 25, y - 8, 6, BLACK);
        y += 38;

        c.setFont(&FreeSans12pt7b);
        const int16_t precipRight = 1304 / 2;
        for (int i = 0; i < dWeatherCount; i++) {
            WeatherDay &wd = dWeather[i];
            char buf[MAX_STR];
            if (wd.label[0])
                snprintf(buf, sizeof(buf), "%s: %s, %d/%d\xC2\xB0""C", wd.label, wd.condition, wd.high, wd.low);
            else
                snprintf(buf, sizeof(buf), "%s, %d/%d\xC2\xB0""C", wd.condition, wd.high, wd.low);

            if (black) { c.setCursor(L + 20, y); c.print(buf); }

            if (wd.rainMm > 0 || wd.snowCm > 0) {
                char precip[48];
                if (wd.snowCm > 0 && wd.rainMm > 0)
                    snprintf(precip, sizeof(precip), "%.0fcm snow + %.0fmm rain (%d%%)", wd.snowCm, wd.rainMm, wd.precipProb);
                else if (wd.snowCm > 0)
                    snprintf(precip, sizeof(precip), "%.0fcm snow (%d%%)", wd.snowCm, wd.precipProb);
                else
                    snprintf(precip, sizeof(precip), "%.0fmm rain (%d%%)", wd.rainMm, wd.precipProb);
                if (red) {
                    int16_t bx, by; uint16_t tw, th2;
                    c.getTextBounds(precip, 0, 0, &bx, &by, &tw, &th2);
                    c.setCursor(precipRight - tw, y);
                    c.print(precip);
                }
            }
            y += 30;

            if (i == 0 && dWalk[0]) {
                char walkLine[MAX_STR];
                snprintf(walkLine, sizeof(walkLine), "Dog walk: %s", dWalk);
                drawMarked(c, L + 20, y, black, red, walkLine);
                y += 40;
            }
        }
        y += 30;
    }

    // Thought (anchored from bottom, above footer)
    if (dThoughtText[0]) {
        // Measure height with a dry run
        int16_t th = 20; // gap above quote
        c.setFont(&FreeSerifBoldItalic24pt7b);
        uint16_t quoteW = 0;
        th += drawWrapped(c, dThoughtText, L, 0, W, 48, false, &quoteW);
        if (dThoughtAuthor[0]) th += 0;
        if (dThoughtContext[0]) {
            th += 65;
            c.setFont(&FreeSans12pt7b);
            int16_t dummy = drawWrapped(c, dThoughtContext, L, 0, W, 28, false);
            th += dummy; // drawWrapped returns final y, started at 0
        }

        const int16_t footerY = 960;
        const int16_t thoughtY = footerY - 40 - th; // 40px above footer
        y = thoughtY;

        y += 20;

        c.setFont(&FreeSerifBoldItalic24pt7b);
        y = drawWrapped(c, dThoughtText, L, y, W, 48, black, &quoteW);

        if (dThoughtAuthor[0]) {
            c.setFont(&FreeSerifItalic18pt7b);
            char attrib[96];
            snprintf(attrib, sizeof(attrib), "- %s", dThoughtAuthor);
            int16_t bx, by; uint16_t tw, th2;
            c.getTextBounds(attrib, 0, 0, &bx, &by, &tw, &th2);
            int16_t ax = L + quoteW - tw;
            if (black) {
                c.setCursor(ax, y);
                c.print(attrib);
            }
            if (red) {
                c.fillRect(ax, y + 10, tw + 20, 3, BLACK);
            }
        }

        if (dThoughtContext[0]) {
            y += 65;
            c.setFont(&FreeSans12pt7b);
            y = drawWrapped(c, dThoughtContext, L, y, W, 28, black);
        }
    }

    // Footer (pinned to bottom-right)
    c.setFont(&FreeSans9pt7b);
    if (dFooter[0]) {
        if (black) {
            int16_t bx, by; uint16_t tw, th2;
            c.getTextBounds(dFooter, 0, 0, &bx, &by, &tw, &th2);
            c.setCursor(1304 - tw - 20, 970);
            c.print(dFooter);
        }
    }
}

static void refreshDisplay()
{
    unsigned long t0 = millis();
    printf("[%6lu] Display: init\r\n", t0);
    EPD_12in48B_Init();

    printf("[%6lu] Display: rendering\r\n", millis());

    // Black, top half
    canvas.setHalf(EinkCanvas::TOP);
    canvas.clearBuffer(0xFF);
    renderScene(canvas, true, false);
    EPD_12in48B_SendBlack1(canvas.getBuffer());

    // Black, bottom half
    canvas.setHalf(EinkCanvas::BOTTOM);
    canvas.clearBuffer(0xFF);
    renderScene(canvas, true, false);
    EPD_12in48B_SendBlack2(canvas.getBuffer());

    // Red, top half
    canvas.setHalf(EinkCanvas::TOP);
    canvas.clearBuffer(0xFF);
    renderScene(canvas, false, true);
    EPD_12in48B_SendRed1(canvas.getBuffer());

    // Red, bottom half
    canvas.setHalf(EinkCanvas::BOTTOM);
    canvas.clearBuffer(0xFF);
    renderScene(canvas, false, true);
    EPD_12in48B_SendRed2(canvas.getBuffer());

    printf("[%6lu] Display: refreshing\r\n", millis());
    EPD_12in48B_TurnOnDisplay();

    printf("[%6lu] Display: done (%lu ms total)\r\n", millis(), millis() - t0);
    EPD_12in48B_Sleep();

    needsRefresh = false;
}

// ── Main ──

void setup()
{
    Serial.begin(115200);
    delay(500);

    printf("=== eink-esp32 ===\r\n");
    printf("Heap: %u free, %u max alloc\r\n",
           ESP.getFreeHeap(), ESP.getMaxAllocHeap());

    DEV_ModuleInit();

    if (!canvas.begin()) {
        printf("Canvas alloc failed!\r\n");
        while (1) delay(1000);
    }
    printf("Canvas: %d bytes\r\n", EinkCanvas::ROW_BYTES * EinkCanvas::HALF_H);

    connectWiFi();

    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setBufferSize(4096);
    mqtt.setCallback(onMqttMessage);
    mqtt.setKeepAlive(60);

    ArduinoOTA.setHostname("eink-display");
    if (strlen(OTA_PASSWORD) > 0)
        ArduinoOTA.setPassword(OTA_PASSWORD);
    ArduinoOTA.onStart([]() { printf("OTA: start\r\n"); });
    ArduinoOTA.onEnd([]()   { printf("OTA: done\r\n"); });
    ArduinoOTA.onError([](ota_error_t e) { printf("OTA: error %u\r\n", e); });
    ArduinoOTA.begin();

    printf("Ready. Waiting for MQTT on %s\r\n", MQTT_TOPIC);
}

void loop()
{
    ArduinoOTA.handle();

    if (WiFi.status() != WL_CONNECTED) {
        connectWiFi();
        return;
    }

    if (!mqtt.connected() && millis() - lastMqttAttempt > 10000) {
        lastMqttAttempt = millis();
        connectMQTT();
    }

    mqtt.loop();

    if (needsRefresh)
        refreshDisplay();
}
