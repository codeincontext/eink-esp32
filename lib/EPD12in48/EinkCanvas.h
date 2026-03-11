#ifndef _EINK_CANVAS_H_
#define _EINK_CANVAS_H_

#include <Adafruit_GFX.h>
#include "DEV_Config.h"

// Canvas that presents full 1304x984 coordinates but renders into
// a half-height buffer (1304x492). Call setHalf() to select which
// vertical half is captured, then draw the full scene. Pixels outside
// the active half are discarded. This lets objects cross the y=492
// boundary naturally.

class EinkCanvas : public Adafruit_GFX {
public:
    static const int16_t FULL_W = 1304;
    static const int16_t FULL_H = 984;
    static const int16_t HALF_H = 492;
    static const int16_t ROW_BYTES = (FULL_W + 7) / 8; // 163

    enum Half { TOP = 0, BOTTOM = 492 };

    EinkCanvas() : Adafruit_GFX(FULL_W, FULL_H), _yOffset(0), _buffer(NULL) {}

    bool begin() {
        _buffer = (uint8_t *)malloc(ROW_BYTES * HALF_H);
        return _buffer != NULL;
    }

    ~EinkCanvas() {
        if (_buffer) free(_buffer);
    }

    void setHalf(Half h) {
        _yOffset = (int16_t)h;
    }

    void clearBuffer(uint8_t fill = 0xFF) {
        if (_buffer) memset(_buffer, fill, ROW_BYTES * HALF_H);
    }

    uint8_t *getBuffer() { return _buffer; }

    void drawPixel(int16_t x, int16_t y, uint16_t color) override {
        if (x < 0 || x >= FULL_W || y < 0 || y >= FULL_H) return;

        int16_t localY = y - _yOffset;
        if (localY < 0 || localY >= HALF_H) return;

        uint32_t byteIdx = (uint32_t)localY * ROW_BYTES + x / 8;
        uint8_t bit = 0x80 >> (x & 7);

        if (color)
            _buffer[byteIdx] |= bit;   // white (1)
        else
            _buffer[byteIdx] &= ~bit;  // black (0)
    }

private:
    int16_t _yOffset;
    uint8_t *_buffer;
};

#endif
